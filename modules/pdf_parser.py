import io
import re
from typing import Dict
import pypdf
import pymupdf  # PyMuPDF

CIRCLE_MAP = {'①': 1, '②': 2, '③': 3, '④': 4, '⑤': 5}

class FileValidationError(Exception):
    """파일 유형 불일치 또는 문항 수 불일치 시 작업을 중단하기 위한 사용자 정의 예외"""
    pass


def extract_text_from_pdf(uploaded_file) -> str:
    """업로드된 PDF 파일에서 전체 텍스트를 추출합니다."""
    uploaded_file.seek(0)
    file_bytes = uploaded_file.read()

    if not file_bytes:
        raise FileValidationError(f"업로드된 '{uploaded_file.name}' 파일이 비어 있습니다.")

    # 1차: pypdf 추출
    try:
        reader = pypdf.PdfReader(io.BytesIO(file_bytes))
        text = "\n".join([page.extract_text() or "" for page in reader.pages])
        if len(text.strip()) > 30:
            return text
    except Exception:
        pass

    # 2차: PyMuPDF 추출
    try:
        doc = pymupdf.open(stream=file_bytes, filetype="pdf")
        text = "\n".join([page.get_text("text") for page in doc])
        if len(text.strip()) > 30:
            return text
    except Exception as e:
        raise FileValidationError(f"'{uploaded_file.name}' 파일을 읽을 수 없습니다. 손상된 PDF이거나 잘못된 형식입니다. ({e})")

    raise FileValidationError(
        f"'{uploaded_file.name}' 파일에서 텍스트를 추출할 수 없습니다. (스캔된 이미지 PDF이거나 빈 문서입니다.)"
    )


def classify_pdf_type(raw_text: str) -> str:
    """
    추출된 PDF 텍스트를 분석하여 문서 유형을 판별합니다.
    반환값: 'answer_sheet' (정답지) | 'question_paper' (문제지) | 'unknown' (알 수 없음)
    """
    # 1. 정답지 특징 검사 (문항-정답-배점 패턴 개수 및 키워드)
    ans_pattern = re.compile(r'(\d(?:\s*\d)?)\s*([①②③④⑤])\s*(\d+(?:\.\d+)?)')
    ans_matches = ans_pattern.findall(raw_text)
    has_answer_keywords = ("정답표" in raw_text) or ("정답" in raw_text and "배" in raw_text and "점" in raw_text)

    # 2. 문제지 특징 검사 (문제 번호 '1. ', '2. ' 패턴 및 문제 지시어 키워드)
    q_pattern = re.compile(r'(?:^|\n)\s*(\d{1,2})\.\s+', re.MULTILINE)
    q_nums = {int(m.group(1)) for m in q_pattern.finditer(raw_text) if 1 <= int(m.group(1)) <= 100}
    question_keywords = ["문제지", "고르시오", "물음에 답하시오", "다음 글", "적절한 것은"]
    q_keyword_hits = sum(1 for kw in question_keywords if kw in raw_text)

    # 판별 로직
    if has_answer_keywords and len(ans_matches) >= 5 and len(q_nums) < 5:
        return "answer_sheet"
    if len(q_nums) >= 5 and q_keyword_hits >= 2:
        return "question_paper"
    if len(ans_matches) >= 10 and len(q_nums) < len(ans_matches) // 2:
        return "answer_sheet"

    return "unknown"


def parse_answer_pdf(uploaded_file) -> Dict[int, Dict[str, int]]:
    """
    정답지 PDF 여부를 먼저 검증한 뒤, 문항 번호·정답·배점을 추출합니다.
    """
    raw_text = extract_text_from_pdf(uploaded_file)
    doc_type = classify_pdf_type(raw_text)

    if doc_type == "question_paper":
        raise FileValidationError(
            f"[파일 업로드 오류] '3. 정답지 파일' 칸에 업로드하신 '{uploaded_file.name}' 파일은 **문제지 PDF**로 판단됩니다. "
            f"올바른 **정답지(정답표) PDF**를 업로드해 주세요."
        )
    elif doc_type == "unknown":
        raise FileValidationError(
            f"[파일 업로드 오류] '3. 정답지 파일' 칸에 업로드하신 '{uploaded_file.name}' 파일에서 정답표 양식(문항 번호, 정답, 배점)을 찾을 수 없습니다. "
            f"올바른 정답지 PDF인지 확인해 주세요."
        )

    answer_dict: Dict[int, Dict[str, int]] = {}

    # 패턴 1: 원문자(①~⑤) 포함 수능 정답표 추출
    pattern_circled = re.compile(r'(\d(?:\s*\d)?)\s*([①②③④⑤])\s*(\d+(?:\.\d+)?)')
    for match in pattern_circled.finditer(raw_text):
        q_num = int(re.sub(r'\s+', '', match.group(1)))
        ans = CIRCLE_MAP[match.group(2)]
        score = int(float(match.group(3)))
        if 1 <= q_num <= 100:
            answer_dict[q_num] = {"answer": ans, "score": score}

    # 패턴 2: 일반 숫자형 정답표 추출 백업
    if len(answer_dict) < 5:
        cleaned_text = raw_text
        for k, v in CIRCLE_MAP.items():
            cleaned_text = cleaned_text.replace(k, f" {v} ")
        pattern_plain = re.compile(r'(\d{1,2})\s*[번\.]?\s+([1-5])\s+(\d+(?:\.\d+)?)\s*점?')
        for match in pattern_plain.finditer(cleaned_text):
            q_num = int(match.group(1))
            ans = int(match.group(2))
            score = int(float(match.group(3)))
            if 1 <= q_num <= 100:
                answer_dict[q_num] = {"answer": ans, "score": score}

    if not answer_dict:
        raise FileValidationError(
            f"[정답지 파싱 실패] '{uploaded_file.name}' 파일에서 문항별 정답과 배점을 추출하지 못했습니다."
        )

    return dict(sorted(answer_dict.items()))


def parse_questions_by_number(uploaded_file) -> Dict[int, str]:
    """
    문제지 PDF 여부를 먼저 검증한 뒤, 각 문항 번호별 지문과 보기를 추출합니다.
    """
    full_text = extract_text_from_pdf(uploaded_file)
    doc_type = classify_pdf_type(full_text)

    if doc_type == "answer_sheet":
        raise FileValidationError(
            f"[파일 업로드 오류] '1. 문제지 파일' 칸에 업로드하신 '{uploaded_file.name}' 파일은 **정답지 PDF**로 판단됩니다. "
            f"올바른 **시험 문제지 PDF**를 업로드해 주세요."
        )
    elif doc_type == "unknown":
        raise FileValidationError(
            f"[파일 업로드 오류] '1. 문제지 파일' 칸에 업로드하신 '{uploaded_file.name}' 파일은 유효한 시험 문제지 양식이 아닙니다. "
            f"문항 번호(1., 2. 등)와 지문이 포함된 문제지 PDF를 업로드해 주세요."
        )

    full_text = re.sub(r'이 문제지에 관한 저작권은.*있습니다\.', '', full_text)
    q_pattern = re.compile(r'(?:^|\n)\s*(\d{1,2})\.\s+(.*?)(?=(?:\n\s*\d{1,2}\.\s+|\Z))', re.DOTALL)
    questions_map: Dict[int, str] = {}

    for match in q_pattern.finditer(full_text):
        q_num = int(match.group(1))
        if 1 <= q_num <= 100 and q_num not in questions_map:
            questions_map[q_num] = f"{q_num}. {match.group(2).strip()}"

    if not questions_map:
        raise FileValidationError(
            f"[문제지 파싱 실패] '{uploaded_file.name}' 파일에서 문항을 추출하지 못했습니다."
        )

    # 장문 독해([41~42], [43~45]) 공통 지문 보강
    for page_text in full_text.split("이 문제지에 관한"):
        if "[41~42]" in page_text or "41." in page_text:
            for q in [41, 42]:
                if q in questions_map and len(questions_map[q]) < 300:
                    questions_map[q] = page_text.strip()
        if "[43~45]" in page_text or "43." in page_text:
            for q in [43, 44, 45]:
                if q in questions_map and len(questions_map[q]) < 300:
                    questions_map[q] = page_text.strip()

    return dict(sorted(questions_map.items()))