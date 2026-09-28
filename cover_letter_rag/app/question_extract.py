"""캡처한 자기소개서 문항 → 문항 목록.

회사 채용 사이트는 로그인해야 문항이 보이거나, 문항이 이미지 · 첨부 양식 안에 있어 복사가 안 되는 경우가 많다.
그래서 학생이 화면을 캡처해 올리면 문항과 글자 수를 뽑아 준다.

모델에게 이미지 속 글을 먼저 그대로 옮기게(transcript) 하고, 문항은 **그 글에 실제로 있는 것만** 남긴다.
글자 수도 옮긴 글에 그 숫자가 있어야 믿는다. 없는 문항을 지어내거나 글자 수를 짐작해 넣는 것을 막는다.
뽑은 문항은 화면에서 학생이 확인하고 고친 뒤에 정한다.

회사 지원서 양식(PDF)도 받는다. 글이 든 PDF 는 글을 꺼내 그 글로 뽑고 **꺼낸 원문과 대조**한다(옮겨 적는
단계가 없어 이미지보다 정확하다). 글이 없는 스캔 PDF 는 페이지에 든 이미지를 꺼내 캡처처럼 읽는다.
"""
from __future__ import annotations

import base64
import io
import re

from pydantic import Field

from app.models import StrictModel

# 공공기관 양식은 상위 5문항 × 하위 2개 + 직무기술서처럼 답칸이 10개를 넘는다(한국중부발전 양식 11칸)
MAX_QUESTIONS = 20
MAX_PDF_PAGES = 5
MAX_PDF_TEXT = 20_000
MAX_PDF_IMAGES = 3
# 이보다 글이 적으면 스캔 PDF 로 본다(쪽 번호 · 머리글만 글로 남은 경우)
MIN_PDF_TEXT = 30

EXTRACT_INSTRUCTIONS = """이미지는 회사 채용 사이트나 지원서 양식을 캡처한 것이다. 자기소개서 문항을 뽑는다.

1. transcript: 이미지에 보이는 글을 위에서 아래로, 줄을 바꿔 가며 그대로 옮긴다. 고치거나 요약하지 않는다.
2. questions: 지원자가 글로 답을 써야 하는 문항만 고른다. 자기소개서 문항과, 직무역량기술서 · 경력기술서처럼 서술형으로
   쓰는 칸도 문항이다. 인적 사항 · 학력 · 자격증 칸, 안내문 · 작성 요령 · 서약 · 메뉴 · 버튼 글자는 뺀다.
   - question: 문항 문장을 이미지에 적힌 그대로 옮긴다. 앞 번호(1. Q1 ① 1-1.)와 글자 수 표기((500자 이내))만 뺀다.
   - group: 하위 문항(1-1, (1), 가.)이면 그 위의 상위 문항 문장을 그대로, 아니면 빈 문자열.
     하위 문항마다 답을 따로 쓰므로 하위 문항 하나하나를 question 으로 내고, 상위 문항 자체는 따로 내지 않는다.
   - limit: 그 문항의 글자 수 제한(숫자만, 1,000자는 1000). 상위 문항의 「각 항목 400자」는 하위 문항마다 400.
     적혀 있지 않거나 읽을 수 없으면 null.
3. 문항이 없으면 questions 를 비운다. 이미지에 없는 문항을 짐작해 만들지 않는다."""


class ExtractedQuestionOut(StrictModel):
    question: str = Field(description='문항 문장. 적힌 그대로, 번호와 글자 수 표기만 뺀다')
    limit: int | None = Field(description='글자 수 제한. 적혀 있지 않거나 읽을 수 없으면 null')
    group: str = Field(default='', description='하위 문항이면 상위 문항 문장, 아니면 빈 문자열')


class QuestionExtractOut(StrictModel):
    transcript: str = Field(description='이미지에 보이는 글 전체를 그대로 옮긴 것')
    questions: list[ExtractedQuestionOut] = Field(default_factory=list)


class QuestionListOut(StrictModel):
    questions: list[ExtractedQuestionOut] = Field(default_factory=list)


TEXT_INSTRUCTIONS = """아래 글은 회사 지원서 양식(PDF)에서 꺼낸 것이다. 자기소개서 문항을 뽑는다.

- 지원자가 글로 답을 써야 하는 문항만 고른다. 자기소개서 문항과, 직무역량기술서 · 경력기술서처럼 서술형으로 쓰는 칸도
  문항이다. 인적 사항 · 학력 · 자격증 칸, 안내문 · 작성 요령 · 서약은 뺀다.
- question: 문항 문장을 글에 적힌 그대로 옮긴다. 앞 번호(1. Q1 ① 1-1.)와 글자 수 표기((500자 이내))만 뺀다.
- group: 하위 문항(1-1, (1), 가.)이면 그 위의 상위 문항 문장을 그대로, 아니면 빈 문자열.
  하위 문항마다 답을 따로 쓰므로 하위 문항 하나하나를 question 으로 내고, 상위 문항 자체는 따로 내지 않는다.
- limit: 그 문항의 글자 수 제한(숫자만, 1,000자는 1000). 상위 문항의 「각 항목 400자」는 하위 문항마다 400.
  적혀 있지 않으면 null.
- 문항이 없으면 비운다. 글에 없는 문항을 짐작해 만들지 않는다."""


class QuestionExtractor:
    """캡처(이미지) · PDF 글 → 문항. 모델 호출만 한다. 대조는 ground_questions 가 한다."""

    def __init__(self, settings) -> None:
        from langchain_openai import ChatOpenAI

        model = ChatOpenAI(
            model=settings.openai_model,
            api_key=settings.openai_api_key,
            use_responses_api=True,
            reasoning_effort='low',
            max_retries=0,
        )
        self._vision = model.with_structured_output(QuestionExtractOut, method='json_schema')
        self._text = model.with_structured_output(QuestionListOut, method='json_schema')

    def from_images(self, images: list[str]) -> QuestionExtractOut:
        from langchain_core.messages import HumanMessage, SystemMessage

        content = [{'type': 'text', 'text': '이 캡처에서 자기소개서 문항을 뽑아 주세요.'}]
        content += [{'type': 'image_url', 'image_url': {'url': url}} for url in images]
        return self._vision.invoke([SystemMessage(content=EXTRACT_INSTRUCTIONS), HumanMessage(content=content)])

    def from_text(self, text: str) -> QuestionExtractOut:
        from langchain_core.messages import HumanMessage, SystemMessage

        out = self._text.invoke([SystemMessage(content=TEXT_INSTRUCTIONS), HumanMessage(content=text)])
        # 원문은 모델이 옮긴 것이 아니라 PDF 에서 꺼낸 글 그대로다 — 대조가 더 믿을 만하다
        return QuestionExtractOut(transcript=text, questions=out.questions)


def build_question_extractor(settings) -> QuestionExtractor:
    return QuestionExtractor(settings)


def read_pdf(data: bytes) -> tuple[str, list[str]]:
    """PDF → (앞 몇 쪽의 글, 글이 없으면 페이지에 든 이미지 data URL). 못 읽으면 ReviewInputError."""
    from pypdf import PdfReader
    from pypdf.errors import PyPdfError

    from app.review_workflow import ReviewInputError

    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted and not reader.decrypt(''):
            raise ReviewInputError('pdf_unreadable')
        pages = list(reader.pages)[:MAX_PDF_PAGES]
        text = '\n'.join(page.extract_text() or '' for page in pages)[:MAX_PDF_TEXT]
        images: list[str] = []
        if len(_squash(text)) < MIN_PDF_TEXT:
            for page in pages:
                for image in page.images:
                    kind = {'jpg': 'jpeg', 'jpeg': 'jpeg', 'png': 'png'}.get(image.name.rsplit('.', 1)[-1].lower())
                    if kind and len(image.data) <= 8 * 1024 * 1024:
                        images.append(f'data:image/{kind};base64,{base64.b64encode(image.data).decode("ascii")}')
                    if len(images) >= MAX_PDF_IMAGES:
                        break
                if len(images) >= MAX_PDF_IMAGES:
                    break
    except ReviewInputError:
        raise
    except (PyPdfError, ValueError, KeyError, TypeError, OSError) as exc:
        raise ReviewInputError('pdf_unreadable') from exc
    return text, images


def extract_questions(extractor, images: list[str]) -> dict:
    """이미지 data URL 들, 또는 PDF data URL 하나 → 대조한 문항. 어느 길로 읽었는지 source 로 알린다."""
    from app.review_workflow import ReviewInputError

    pdfs = [url for url in images if url.startswith('data:application/pdf;base64,')]
    if not pdfs:
        return {**ground_questions(extractor.from_images(images)), 'source': 'image'}
    if len(images) != 1:
        raise ReviewInputError('pdf_with_other_files')
    text, page_images = read_pdf(base64.b64decode(pdfs[0].split(',', 1)[1]))
    if len(_squash(text)) >= MIN_PDF_TEXT:
        return {**ground_questions(extractor.from_text(text)), 'source': 'pdf_text'}
    if page_images:
        return {**ground_questions(extractor.from_images(page_images)), 'source': 'pdf_scan'}
    raise ReviewInputError('pdf_no_text')


def _squash(text: str) -> str:
    return re.sub(r'\s+', '', str(text or ''))


def _limit_in(transcript: str, limit: int | None) -> int | None:
    """옮긴 글에 그 숫자가 「N자」 꼴로 있을 때만 글자 수로 믿는다(1,000자 · 1000자 둘 다)."""
    if limit is None or not 50 <= limit <= 5000:
        return None
    pattern = rf'(?<![\d,]){limit:,}\s*자|(?<![\d,]){limit}\s*자'
    return limit if re.search(pattern, transcript) else None


def _clean_group(text: str) -> str:
    """상위 문항에서 글자 수 안내(「[각 항목 400자 이내 기입]」)와 「아래 항목에 따라」 꼬리를 뗀다. 문맥만 남긴다."""
    text = re.sub(r'\s*[\[(][^\])]*\d+\s*자[^\])]*[\])]\s*$', '', str(text or '').strip())
    text = re.sub(r'\s*(에 대해)?\s*아래 항목에 따라.*$', '', text)
    text = re.sub(r'^\s*(\d{1,2}[.)]|[①-⑩]|Q\d{1,2}[.)]?)\s*', '', text)  # 앞 번호
    return re.sub(r'(을|를)$', '', text.strip()).strip()


def ground_questions(extracted: QuestionExtractOut) -> dict:
    """옮긴 글에 실제로 있는 문항만 남긴다. 화면에 줄 모양으로 돌려준다."""
    transcript = extracted.transcript or ''
    haystack = _squash(transcript)
    kept, seen, dropped = [], set(), 0
    for item in extracted.questions:
        question = item.question.strip()
        key = _squash(question)
        if len(key) < 4 or key not in haystack or key in seen:
            dropped += 1
            continue
        seen.add(key)
        # 상위 문항도 원문에 있어야 붙인다. 하위 문항만으로는 「당시」 「해당 방법」이 무엇인지 모른다
        group = _clean_group(item.group)
        if group and _squash(group) in haystack:
            question = f'{group} › {question}'
        kept.append({'question': question, 'limit': _limit_in(transcript, item.limit)})
        if len(kept) >= MAX_QUESTIONS:
            break
    return {'questions': kept, 'dropped': dropped, 'read_text': bool(haystack)}
