import io
import pandas as pd
from typing import Dict, Any

def generate_excel_bytes(result_df: pd.DataFrame, stats: Dict[str, Any]) -> bytes:
    """
    요구사항 3의 엑셀 시트 레이아웃(상단: 전체 학생 성적 개요 / 하단: 학생별 점수 및 문제별 정답 여부)을 생성합니다.
    """
    output = io.BytesIO()
    
    # 내부 조회용 컬럼 제외하고 출력용 데이터프레임 생성
    export_df = result_df.drop(
        columns=["student_id_num", "row_order_num", "틀린문항"],
        errors="ignore"
    )

    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        # 1. 상단: 전체 학생 성적 개요
        summary_df = pd.DataFrame({
            "평균": [stats["mean"]],
            "중앙값": [stats["median"]],
            "표준 편차": [stats["std_sample"]],
            "가장 많이 틀린 문항 번호 3개": [", ".join(f"{q}번" for q in stats["top3_wrong"])]
        })
        summary_df.to_excel(writer, index=False, sheet_name="채점결과", startrow=1)

        # 2. 하단: 각 학생의 점수 및 각 문제별 정답 여부 (O/X)
        export_df.to_excel(writer, index=False, sheet_name="채점결과", startrow=5)

        worksheet = writer.sheets["채점결과"]
        worksheet["A1"] = "■ 전체 학생 성적 개요"
        worksheet["A5"] = "■ 학생별 점수 및 각 문제별 정답 여부 (O: 정답, X: 오답)"

    return output.getvalue()