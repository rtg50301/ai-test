import io
import re
from typing import Dict
import pypdf
import pymupdf

CIRCLE_MAP = {'①': 1, '②': 2, '③': 3, '④': 4, '⑤': 5}

def extract_text_from_pdf(uploaded_file) -> str:
    """업로드된 PDF 파일에서 전체 텍스트를 추출합니다."""
    uploaded_file.seek(0)
    file_bytes = uploaded_file.read()
    
    # pypdf 우선 추출 (수능 다단 레이아웃 보존에 유리)
    try:
        reader = pypdf.PdfReader(io.BytesIO(file_bytes))
        text = "\n".join([page.extract_text() or "" for page in reader.pages])
        if len(text.strip()) > 50:
            return text
    except Exception:
        pass

    # 백업: PyMuPDF 추출
    doc = pymupdf.open(stream=file_bytes, filetype="pdf")
    return "\n".join([page.get_text("text") for page in doc])


def parse_answer_pdf(uploaded_file) -> Dict[int, Dict[str, int]]:
    """
    수능 영어 정답표 PDF(다단 표 구조)에서 문항 번호, 정답(1~5), 배점(2~3)을 실시간 추출합니다.
    반환 예시: {1: {'answer': 3, 'score': 2}, ..., 45: {'answer': 5, 'score': 2}}
    """
    raw_text = extract_text_from_pdf(uploaded_file)
    answer_dict: Dict[int, Dict[str, int]] = {}

    # 패턴 1: 수능 정답표 특화 정규식 (예: "1 3 ② 3" -> 문항 13, 정답 2, 배점 3)
    pattern_circled = re.compile(r'(\d(?:\s*\d)?)\s*([①②③④⑤])\s*(\d+(?:\.\d+)?)')
    for match in pattern_circled.finditer(raw_text):
        q_num = int(re.sub(r'\s+', '', match.group(1)))
        ans = CIRCLE_MAP[match.group(2)]
        score = int(float(match.group(3)))
        if 1 <= q_num <= 100:
            answer_dict[q_num] = {"answer": ans, "score": score}

    # 패턴 2: 일반 숫자형 정답표 대응 백업 (원문자 없이 "1 3 2" 형태로 적힌 PDF일 경우)
    if len(answer_dict) < 10:
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
        raise ValueError("정답 PDF에서 문항 번호, 정답, 배점을 추출하지 못했습니다. 파일 형식을 확인해 주세요.")

    return dict(sorted(answer_dict.items()))


def parse_questions_by_number(uploaded_file) -> Dict[int, str]:
    """
    문제지 PDF에서 1번~45번 각 문항의 지문과 보기를 문항 번호별로 분리하여 저장합니다.
    """
    full_text = extract_text_from_pdf(uploaded_file)
    
    # 자간 벌어짐 현상(예: 'm o r a l') 완화 및 불필요한 바닥글 제거
    full_text = re.sub(r'이 문제지에 관한 저작권은.*있습니다\.', '', full_text)
    
    q_pattern = re.compile(r'(?:^|\n)\s*(\d{1,2})\.\s+(.*?)(?=(?:\n\s*\d{1,2}\.\s+|\Z))', re.DOTALL)
    questions_map: Dict[int, str] = {}

    for match in q_pattern.finditer(full_text):
        q_num = int(match.group(1))
        if 1 <= q_num <= 45 and q_num not in questions_map:
            questions_map[q_num] = f"{q_num}. {match.group(2).strip()}"

    # 장문 독해([41~42], [43~45])와 같이 공통 지문이 문항 번호 앞에 있는 경우 보강
    for page_text in full_text.split("이 문제지에 관한"):
        if "[41~42]" in page_text or "41." in page_text:
            for q in [41, 42]:
                if q in questions_map and len(questions_map[q]) < 300:
                    questions_map[q] = page_text.strip()
        if "[43~45]" in page_text or "43." in page_text:
            for q in [43, 44, 45]:
                if q in questions_map and len(questions_map[q]) < 300:
                    questions_map[q] = page_text.strip()

    return questions_map