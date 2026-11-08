import re
import pandas as pd
import numpy as np
from typing import Dict, Any, Tuple

CIRCLE_MAP = {'①': 1, '②': 2, '③': 3, '④': 4, '⑤': 5}

def load_omr_data(uploaded_file) -> pd.DataFrame:
    """엑셀(xlsx/xls) 또는 CSV 형태의 학생 OMR 답안지를 로드합니다."""
    uploaded_file.seek(0)
    if uploaded_file.name.lower().endswith('.csv'):
        try:
            return pd.read_csv(uploaded_file, encoding='utf-8')
        except UnicodeDecodeError:
            uploaded_file.seek(0)
            return pd.read_csv(uploaded_file, encoding='cp949')
    else:
        xls = pd.ExcelFile(uploaded_file)
        # 'OMR_응답' 시트가 있으면 우선 로드, 없으면 첫 번째 시트 로드
        sheet = 'OMR_응답' if 'OMR_응답' in xls.sheet_names else xls.sheet_names[0]
        return pd.read_excel(uploaded_file, sheet_name=sheet)


def grade_students(
    omr_df: pd.DataFrame,
    answer_key: Dict[int, Dict[str, int]]
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """
    학생 답안지(OMR)와 정답지를 비교하여 학생별 총점, 문항별 정오표(O/X), 전체 통계를 산출합니다.
    """
    df = omr_df.copy()
    student_col = df.columns[0]  # '학생명' 또는 첫 번째 식별자 컬럼

    # 문항 번호 컬럼 매핑 (예: 'Q01' -> 1, 'Q45' -> 45, '1번' -> 1)
    q_col_map = {}
    for col in df.columns[1:]:
        nums = re.findall(r'\d+', str(col))
        if nums:
            q_num = int(nums[0])
            if q_num in answer_key:
                q_col_map[q_num] = col

    graded_rows = []
    wrong_counts = {q_num: 0 for q_num in sorted(answer_key.keys())}

    for idx, row in df.iterrows():
        raw_name = str(row[student_col]).strip()
        id_nums = re.findall(r'\d+', raw_name)
        student_id_num = int(id_nums[0]) if id_nums else (idx + 1)
        row_order_num = idx + 1  # 1번째 행부터의 순번 (1~120)

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

            # 컬럼명을 Q01 ~ Q45 형태로 통일하여 가독성 확보
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

    # 가장 많이 틀린 문항 상위 3개 (오답자 수 내림차순, 문항번호 오름차순)
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
        "total_students": len(result_df)
    }

    return result_df, stats