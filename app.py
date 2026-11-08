import streamlit as st

st.set_page_config(page_title="oo 학원 평가 도우미", page_icon="🎓", layout="wide")

# 상단 페이지 이동 버튼 영역
col_nav1, col_nav2, _ = st.columns([1.5, 1.5, 7])
with col_nav1:
    st.page_link("app.py", label="🏠 1페이지 (서비스 소개)", use_container_width=True)
with col_nav2:
    st.page_link("pages/analysis.py", label="📊 2페이지 (채점 및 AI 챗봇)", use_container_width=True)

st.divider()

# 중앙 랜딩 섹션
_, center_col, _ = st.columns([2, 6, 2])
with center_col:
    st.markdown("<div style='text-align: center;'>", unsafe_allow_html=True)
    # 가천대 로고 (images/logo.png가 없을 경우 기본 텍스트/아이콘 표시)
    try:
        st.image("./images/logo.png", width=220)
    except Exception:
        st.markdown("### 🏫 GACHON UNIVERSITY AI AGENT")
    
    st.title("oo 학원 평가 도우미")
    st.subheader("학생 모의고사 자동 채점 & AI 맞춤형 문제 생성 에이전트")
    st.markdown("</div>", unsafe_allow_html=True)

    st.info(
        """
        **주요 지원 기능**
        1. **자동 채점 시스템:** 문제지 PDF, 학생 OMR 데이터, 정답지 PDF를 업로드하면 문항별 정답과 배점을 자동으로 추출해 즉시 채점합니다.
        2. **엑셀 성적표 추출:** 전체 성적 개요(평균, 중앙값, 표준편차, 최다 오답 문항 3개)와 학생별 정오표를 엑셀 파일로 다운로드합니다.
        3. **AI 데이터 분석 & 문제 생성 챗봇:** 성적 통계 질의응답부터 오답률 1위 문항과 유사한 유형의 신규 문제 생성까지 대화형으로 지원합니다.
        """
    )

    st.page_link(
        "pages/analysis.py",
        label="🚀 데이터 입력 및 분석 시작하기 (2페이지로 이동)",
        use_container_width=True
    )