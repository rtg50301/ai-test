import os
import streamlit as st

st.set_page_config(page_title="데이터 분석 및 챗봇 - oo 학원 평가 도우미", page_icon="📊", layout="wide")

with st.spinner("페이지를 불러오는 중..."):
    from dotenv import load_dotenv
    from langchain_core.messages import HumanMessage, AIMessage

    # [변경 1] FileValidationError 추가 임포트
    from modules.pdf_parser import (
        parse_answer_pdf,
        parse_questions_by_number,
        FileValidationError,
    )
    from modules.grader import load_omr_data, grade_students
    from modules.excel_exporter import generate_excel_bytes
    from modules.agent import build_grading_agent

    load_dotenv()

# 상단 페이지 이동 버튼
col_nav1, col_nav2, _ = st.columns([1.5, 1.5, 7])
with col_nav1:
    st.page_link("app.py", label="🏠 1페이지 (서비스 소개)", use_container_width=True)
with col_nav2:
    st.page_link("pages/analysis.py", label="📊 2페이지 (채점 및 AI 챗봇)", use_container_width=True)

# 세션 상태 초기화 ([변경 2] validation_error 키 추가)
for key, default_val in {
    "is_graded": False,
    "messages": [],
    "excel_bytes": None,
    "agent": None,
    "stats": None,
    "grading_complete": False,
    "validation_error": None,
}.items():
    if key not in st.session_state:
        st.session_state[key] = default_val

# 환경변수(.env) 우선 확인 후 st.secrets 확인 (불필요한 Secrets 경고가 뜨지 않도록 개선)
api_key = os.getenv("OPENAI_API_KEY", "")
if not api_key:
    try:
        api_key = st.secrets.get("OPENAI_API_KEY", "")
    except Exception:
        api_key = ""

# 좌측 사이드바: 파일 업로드 및 버튼
with st.sidebar:
    st.header("📂 데이터 업로드")
    question_file = st.file_uploader("1. 문제지 파일 (PDF)", type=["pdf"])
    omr_file = st.file_uploader("2. 학생 OMR 결과 데이터 (Excel/CSV)", type=["xlsx", "xls", "csv"])
    answer_file = st.file_uploader("3. 정답지 파일 (PDF)", type=["pdf"])

    start_btn = st.button(
        "🔍 분석 시작 버튼",
        use_container_width=True,
        type="primary",
        disabled=not (question_file and omr_file and answer_file)
    )

    st.divider()

    # 채점 완료 시에만 엑셀 추출 버튼 활성화
    if st.session_state.is_graded and st.session_state.excel_bytes:
        st.download_button(
            label="📥 엑셀 추출 버튼",
            data=st.session_state.excel_bytes,
            file_name="모의고사_자동채점_결과.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True
        )
    else:
        st.button("📥 엑셀 추출 버튼", disabled=True, use_container_width=True)

# 채점 완료 또는 검증 오류 알림 표시
if st.session_state.grading_complete:
    st.session_state.grading_complete = False
    st.success("자동 채점 완료! 이제 엑셀 추출 및 채팅이 가능합니다.")

# [변경 3] 파일 검증 실패 시 중단 사유를 화면 상단에 명확히 표시
if st.session_state.validation_error:
    st.error(f"🛑 **작업 중단 사유**\n\n{st.session_state.validation_error}")

if start_btn:
    st.session_state.validation_error = None
    if not api_key:
        st.error("OpenAI API Key를 환경변수(.env) 또는 Streamlit Secrets에 설정해 주세요.")
    else:
        try:
            with st.spinner("파일 유효성 검증 및 학생 답안 자동 채점 중..."):
                # 1. 문제지 및 정답지 PDF 유형 판별 & 실시간 파싱
                questions_map = parse_questions_by_number(question_file)
                answer_key = parse_answer_pdf(answer_file)

                # 2. 학생 OMR 답안 로드
                omr_df = load_omr_data(omr_file)

                # [변경 4] questions_map을 함께 전달하여 문제지·정답지·OMR 문항 개수 일치 검증
                result_df, stats = grade_students(omr_df, answer_key, questions_map=questions_map)

                # 3. 엑셀 추출용 바이너리 생성
                excel_bytes = generate_excel_bytes(result_df, stats)

            with st.spinner("AI 에이전트를 초기화하는 중..."):
                agent = build_grading_agent(result_df, stats, questions_map, answer_key, api_key)

            # 상태 저장 및 활성화
            st.session_state.is_graded = True
            st.session_state.excel_bytes = excel_bytes
            st.session_state.agent = agent
            st.session_state.stats = stats
            st.session_state.messages = [
                {
                    "role": "assistant",
                    "content": (
                        f"파일 검증(총 **{stats.get('total_questions', len(answer_key))}문항** 일치) 및 "
                        f"**{stats['total_students']}명**의 학생 답안지 채점이 완료되었습니다! "
                        f"(전체 평균: **{stats['mean']}점**, 중앙값: **{stats['median']}점**)\n\n"
                        "성적 통계 질문, 특정 학생 점수 조회, 또는 오답률 1위 문항 기반 유사 문제 생성을 요청해 주세요."
                    )
                }
            ]
            st.session_state.grading_complete = True
            st.rerun()

        # [변경 5] 잘못된 파일 또는 문항 수 불일치 시 작업 중단 및 상태 초기화 후 rerun
        except FileValidationError as ve:
            st.session_state.is_graded = False
            st.session_state.excel_bytes = None
            st.session_state.agent = None
            st.session_state.messages = []
            st.session_state.validation_error = str(ve)
            st.rerun()

        except Exception as e:
            st.session_state.is_graded = False
            st.session_state.excel_bytes = None
            st.session_state.agent = None
            st.session_state.messages = []
            st.session_state.validation_error = f"분석 중 예기치 않은 오류가 발생했습니다: {e}"
            st.rerun()

# 우측 메인 영역: 채팅 내역 및 채팅 입력
st.subheader("💬 채점 결과 분석 & 유사 문제 생성 AI 챗봇")

if not st.session_state.is_graded:
    st.info("좌측 사이드바에서 문제지 PDF, OMR 엑셀 파일, 정답지 PDF를 업로드한 뒤 **[분석 시작 버튼]**을 클릭해 주세요.")

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

user_query = st.chat_input(
    "채점 결과에 대해 질문하거나 유사 문제 생성을 요청하세요...",
    disabled=not st.session_state.is_graded
)

if user_query and st.session_state.is_graded:
    st.session_state.messages.append({"role": "user", "content": user_query})
    with st.chat_message("user"):
        st.markdown(user_query)

    # 프롬프트 인젝션 키워드 1차 즉시 방어
    q_lower = user_query.lower()
    injection_keywords = [
        "tool", "툴", "연결된 도구", "어떤 도구", "무슨 도구",
        "function", "프롬프트", "prompt", "instruction", "시스템 구조"
    ]

    with st.chat_message("assistant"):
        if any(k in q_lower for k in injection_keywords):
            reply = "보안 정책상 시스템 내부 구조나 연결된 도구(Tool) 정보는 공개할 수 없습니다. 모의고사 채점 결과 분석이나 유사 문제 생성과 관련된 질문을 입력해 주세요."
            st.markdown(reply)
        else:
            with st.spinner("답변을 생성하고 있습니다..."):
                try:
                    lc_messages = [
                        HumanMessage(content=m["content"]) if m["role"] == "user" else AIMessage(content=m["content"])
                        for m in st.session_state.messages
                    ]
                    response = st.session_state.agent.invoke({"messages": lc_messages})
                    reply = response["messages"][-1].content
                except Exception as e:
                    reply = f"답변 생성 중 일시적인 오류가 발생했습니다. 잠시 후 다시 시도해 주세요. ({e})"
                st.markdown(reply)

    st.session_state.messages.append({"role": "assistant", "content": reply})