import re
import pandas as pd
from typing import Dict, Any, Tuple
from modules.pdf_parser import FileValidationError

CIRCLE_MAP = {'①': 1, '②': 2, '③': 3, '④': 4, '⑤': 5}

def load_omr_data(uploaded_file) -> pd.DataFrame:
    """엑셀(xlsx/xls) 또는 CSV 형태의 학생 OMR 답안지를 로드하고 기본 구조를 검증합니다."""
    uploaded_file.seek(0)
    try:
        if uploaded_file.name.lower().endswith('.csv'):
            try:
                df = pd.read_csv(uploaded_file, encoding='utf-8')
            except UnicodeDecodeError:
                uploaded_file.seek(0)
                df = pd.read_csv(uploaded_file, encoding='cp949')
        else:
            xls = pd.ExcelFile(uploaded_file)
            sheet = 'OMR_응답' if 'OMR_응답' in xls.sheet_names else xls.sheet_names[0]
            df = pd.read_excel(uploaded_file, sheet_name=sheet)
    except Exception as e:
        raise FileValidationError(
            f"[파일 업로드 오류] '2. 학생 OMR 결과 데이터' 칸의 '{uploaded_file.name}' 파일을 읽을 수 없습니다. ({e})"
        )

    if df.empty or len(df.columns) < 2:
        raise FileValidationError(
            f"[OMR 데이터 오류] '{uploaded_file.name}' 파일에 유효한 학생 답안 데이터가 없거나 컬럼 구조가 올바르지 않습니다."
        )

    return df


def extract_omr_question_map(omr_df: pd.DataFrame) -> Dict[int, str]:
    """OMR 데이터프레임에서 문항 번호 컬럼(예: Q01~Q45)을 추출하고 유효성을 검사합니다."""
    q_col_map: Dict[int, str] = {}
    for col in omr_df.columns[1:]:
        nums = re.findall(r'\d+', str(col))
        if nums:
            q_num = int(nums[0])
            if 1 <= q_num <= 100 and q_num not in q_col_map:
                q_col_map[q_num] = col

    if not q_col_map:
        raise FileValidationError(
            "[OMR 데이터 오류] 업로드된 엑셀/CSV 파일에서 문항 번호 컬럼(예: Q01, Q02... 또는 1번, 2번...)을 찾을 수 없습니다. "
            "학생 답안지 파일이 맞는지 확인해 주세요."
        )

    return dict(sorted(q_col_map.items()))


def validate_question_consistency(
    questions_map: Dict[int, str],
    answer_key: Dict[int, Dict[str, int]],
    omr_df: pd.DataFrame
) -> Dict[int, str]:
    """
    문제지 PDF, 정답지 PDF, OMR 데이터 3개 파일의 문항 개수와 문항 번호 구성이 완벽히 일치하는지 검증합니다.
    불일치 시 구체적인 사유와 함께 FileValidationError를 발생시켜 작업을 중단합니다.
    """
    omr_q_map = extract_omr_question_map(omr_df)

    q_set = set(questions_map.keys())
    a_set = set(answer_key.keys())
    o_set = set(omr_q_map.keys())

    q_cnt, a_cnt, o_cnt = len(q_set), len(a_set), len(o_set)

    # 1. 문항 개수가 서로 다른 경우
    if not (q_cnt == a_cnt == o_cnt):
        details = []
        if q_cnt != a_cnt:
            diff_qa = sorted(q_set ^ a_set)
            details.append(f"문제지↔정답지 차이 문항: {diff_qa[:10]}")
        if a_cnt != o_cnt:
            diff_ao = sorted(a_set ^ o_set)
            details.append(f"정답지↔OMR 차이 문항: {diff_ao[:10]}")
        detail_str = f" ({' / '.join(details)})" if details else ""

        raise FileValidationError(
            f"[문항 개수 불일치] 업로드된 파일들의 문항 개수가 일치하지 않아 채점 작업을 중단합니다.\n"
            f"- 문제지 PDF: **{q_cnt}문항**\n"
            f"- 정답지 PDF: **{a_cnt}문항**\n"
            f"- 학생 OMR 데이터: **{o_cnt}문항**{detail_str}\n\n"
            f"동일한 시험의 문제지, 정답지, OMR 파일인지 확인해 주세요."
        )

    # 2. 문항 개수는 같지만 문항 번호 구성(예: 1~45번)이 서로 다른 경우
    if not (q_set == a_set == o_set):
        diff_all = sorted((q_set | a_set | o_set) - (q_set & a_set & o_set))
        raise FileValidationError(
            f"[문항 번호 불일치] 세 파일의 총 문항 수는 {a_cnt}개로 같으나, 포함된 문항 번호가 서로 일치하지 않습니다. "
            f"(불일치 문항 번호: {diff_all[:10]})\n"
            f"동일한 시험의 파일인지 확인해 주세요."
        )

    return omr_q_map


def grade_students(
    omr_df: pd.DataFrame,
    answer_key: Dict[int, Dict[str, int]],
    questions_map: Dict[int, str] = None
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """
    문항 수 및 문항 번호 일치를 먼저 검증한 뒤, 학생 답안지(OMR)를 자동 채점합니다.
    """
    if questions_map is not None:
        q_col_map = validate_question_consistency(questions_map, answer_key, omr_df)
    else:
        q_col_map = extract_omr_question_map(omr_df)

    df = omr_df.copy()
    student_col = df.columns[0]

    graded_rows = []
    wrong_counts = {q_num: 0 for q_num in sorted(answer_key.keys())}

    for idx, row in df.iterrows():
        raw_name = str(row[student_col]).strip()
        id_nums = re.findall(r'\d+', raw_name)
        student_id_num = int(id_nums[0]) if id_nums else (idx + 1)
        row_order_num = idx + 1

        total_score = 0
        row_result = {
            "학생명": raw_name,
            "student_id_num": student_id_num,
            "row_order_num": row_order_num,
            "총점": 0
        }
        wrong_questions = []

        for q_num in sorted(answer_key.keys()):
            correct_ans = int(answer_key[q_num]["answer"])
            score = int(answer_key[q_num]["score"])
            col_name = q_col_map.get(q_num)

            raw_val = row[col_name] if col_name in row else None
            if str(raw_val).strip() in CIRCLE_MAP:
                student_ans = CIRCLE_MAP[str(raw_val).strip()]
            else:
                try:
                    student_ans = int(float(raw_val))
                except (ValueError, TypeError):
                    student_ans = -1

            col_label = f"Q{q_num:02d}"
            if student_ans == correct_ans:
                total_score += score
                row_result[col_label] = "O"
            else:
                row_result[col_label] = "X"
                wrong_counts[q_num] += 1
                wrong_questions.append(q_num)

        row_result["총점"] = total_score
        row_result["틀린문항"] = wrong_questions
        graded_rows.append(row_result)

    result_df = pd.DataFrame(graded_rows)
    scores = result_df["총점"].astype(float)

    sorted_wrong = sorted(wrong_counts.items(), key=lambda x: (-x[1], x[0]))
    top3_wrong = [q for q, _ in sorted_wrong[:3]]

    min_score = int(scores.min())
    max_score = int(scores.max())
    lowest_students = result_df[result_df["총점"] == min_score]["학생명"].tolist()
    highest_students = result_df[result_df["총점"] == max_score]["학생명"].tolist()

    stats = {
        "mean": round(float(scores.mean()), 2),
        "median": round(float(scores.median()), 2),
        "std_sample": round(float(scores.std(ddof=1)), 2) if len(scores) > 1 else 0.0,
        "std_pop": round(float(scores.std(ddof=0)), 2),
        "top3_wrong": top3_wrong,
        "wrong_counts": wrong_counts,
        "min_score": min_score,
        "lowest_students": lowest_students,
        "max_score": max_score,
        "highest_students": highest_students,
        "total_students": len(result_df),
        "total_questions": len(answer_key)
    }

    return result_df, stats