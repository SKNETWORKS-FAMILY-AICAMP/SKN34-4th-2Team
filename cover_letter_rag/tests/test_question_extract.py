"""캡처 → 자기소개서 문항. 옮긴 글에 없는 문항 · 숫자는 믿지 않는다."""
from fastapi.testclient import TestClient

from app.main import app, get_question_extractor
from app.question_extract import ExtractedQuestionOut, QuestionExtractOut, QuestionListOut, ground_questions

TRANSCRIPT = """지원서 작성
[자기소개서]
1. 클라우드랩에 지원한 이유와 입사 후 포부를 기술하시오. (공백 포함 1,000자 이내)
2. 본인이 주도적으로 문제를 해결한 경험을 서술하시오. (600자)
※ 작성 요령: 구체적으로 작성해 주세요.
[저장] [제출]"""


def q(question, limit=None):
    return ExtractedQuestionOut(question=question, limit=limit)


def test_keeps_questions_that_are_in_the_transcript_and_trusts_only_written_limits():
    result = ground_questions(QuestionExtractOut(transcript=TRANSCRIPT, questions=[
        q('클라우드랩에 지원한 이유와 입사 후 포부를 기술하시오.', 1000),
        q('본인이 주도적으로 문제를 해결한 경험을 서술하시오.', 800),   # 이미지엔 600자 — 짐작한 숫자
        q('입사 후 10년 뒤 모습을 서술하시오.', 500),                   # 이미지에 없는 문항
        q('클라우드랩에 지원한 이유와 입사 후 포부를 기술하시오.', 1000),  # 같은 문항 두 번
    ]))
    assert result['questions'] == [
        {'question': '클라우드랩에 지원한 이유와 입사 후 포부를 기술하시오.', 'limit': 1000},
        {'question': '본인이 주도적으로 문제를 해결한 경험을 서술하시오.', 'limit': None},
    ]
    assert result['dropped'] == 2
    assert result['read_text'] is True


def test_six_hundred_is_not_read_out_of_sixteen_hundred():
    result = ground_questions(QuestionExtractOut(
        transcript='1. 지원 동기를 쓰시오. (1600자)', questions=[q('지원 동기를 쓰시오.', 600)],
    ))
    assert result['questions'] == [{'question': '지원 동기를 쓰시오.', 'limit': None}]


class FakeExtractor:
    def __init__(self, out):
        self.out = out
        self.images, self.texts = [], []

    def from_images(self, images):
        self.images.extend(images)
        return self.out

    def from_text(self, text):
        self.texts.append(text)
        return QuestionExtractOut(transcript=text, questions=self.out.questions)


def text_pdf(lines):
    """글이 든 한 쪽짜리 PDF. 표준 글꼴이라 ASCII 만 쓴다(한글 문항은 다른 테스트가 본다)."""
    stream = 'BT /F1 12 Tf 72 720 Td 14 TL ' + ' '.join(f'({line}) Tj T*' for line in lines) + ' ET'
    objects = [
        '<< /Type /Catalog /Pages 2 0 R >>',
        '<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
        '<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>',
        f'<< /Length {len(stream)} >>\nstream\n{stream}\nendstream',
        '<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',
    ]
    out, offsets = '%PDF-1.4\n', []
    for i, body in enumerate(objects, 1):
        offsets.append(len(out))
        out += f'{i} 0 obj\n{body}\nendobj\n'
    xref = len(out)
    out += f'xref\n0 {len(objects) + 1}\n0000000000 65535 f \n' + ''.join(f'{o:010d} 00000 n \n' for o in offsets)
    out += f'trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF'
    return out.encode('latin-1')


def pdf_url(data):
    import base64
    return 'data:application/pdf;base64,' + base64.b64encode(data).decode()


def post(extractor, images):
    app.dependency_overrides[get_question_extractor] = lambda: extractor
    try:
        return TestClient(app).post('/api/v1/resumes/question-extract/proxy', json={'images': images})
    finally:
        app.dependency_overrides.clear()


def test_endpoint_takes_only_image_or_pdf_data_urls():
    extractor = FakeExtractor(QuestionExtractOut(transcript=TRANSCRIPT, questions=[q('본인이 주도적으로 문제를 해결한 경험을 서술하시오.', 600)]))
    ok = post(extractor, ['data:image/png;base64,AAAA'])
    assert ok.status_code == 200
    assert ok.json() == {'questions': [{'question': '본인이 주도적으로 문제를 해결한 경험을 서술하시오.', 'limit': 600}],
                         'dropped': 0, 'read_text': True, 'source': 'image'}
    assert extractor.images == ['data:image/png;base64,AAAA']
    assert post(extractor, ['https://example.com/a.png']).status_code == 422
    assert post(extractor, []).status_code == 422


def test_text_pdf_is_read_from_its_own_text_not_from_a_picture():
    lines = ['Application form', '1. Why do you want to join our team and what will you do?', '2. Describe a problem you solved.']
    extractor = FakeExtractor(QuestionListOut(questions=[
        q('Why do you want to join our team and what will you do?'), q('Tell us about your hobbies.'),
    ]))
    response = post(extractor, [pdf_url(text_pdf(lines))])
    assert response.status_code == 200, response.text
    data = response.json()
    assert data['source'] == 'pdf_text'
    assert data['questions'] == [{'question': 'Why do you want to join our team and what will you do?', 'limit': None}]
    assert data['dropped'] == 1
    assert 'Describe a problem you solved.' in extractor.texts[0]
    assert extractor.images == []


def test_blank_encrypted_or_broken_pdf_asks_for_a_capture():
    from io import BytesIO

    from pypdf import PdfWriter

    def build(encrypt=False):
        writer = PdfWriter()
        writer.add_blank_page(width=612, height=792)
        if encrypt:
            writer.encrypt('secret')
        buffer = BytesIO()
        writer.write(buffer)
        return buffer.getvalue()

    extractor = FakeExtractor(QuestionListOut())
    blank = post(extractor, [pdf_url(build())])
    assert blank.status_code == 422 and blank.json()['detail'] == 'pdf_no_text'
    locked = post(extractor, [pdf_url(build(encrypt=True))])
    assert locked.status_code == 422 and locked.json()['detail'] == 'pdf_unreadable'
    broken = post(extractor, [pdf_url(b'not a pdf at all')])
    assert broken.status_code == 422 and broken.json()['detail'] == 'pdf_unreadable'
    mixed = post(extractor, [pdf_url(build()), 'data:image/png;base64,AAAA'])
    assert mixed.status_code == 422 and mixed.json()['detail'] == 'pdf_with_other_files'


def test_sub_questions_carry_their_parent_and_shared_limit():
    transcript = """□ 자기소개서
1. 목표 달성 과정에서 마주한 문제를 해결한 경험에 대해 아래 항목에 따라 작성해 주시기
바랍니다. [각 항목 400자 이내 기입]
 2-1. 당시 달성해야 하는 목표는 무엇이었으며, 목표를 달성해야 하는 이유를 작성해 주시기 바랍니다.
 2-2. 목표 달성 과정에서 발생한 문제와 그 원인을 작성해 주시기 바랍니다."""
    parent = '1. 목표 달성 과정에서 마주한 문제를 해결한 경험에 대해 아래 항목에 따라 작성해 주시기 바랍니다. [각 항목 400자 이내 기입]'
    result = ground_questions(QuestionExtractOut(transcript=transcript, questions=[
        ExtractedQuestionOut(question='당시 달성해야 하는 목표는 무엇이었으며, 목표를 달성해야 하는 이유를 작성해 주시기 바랍니다.',
                             limit=400, group=parent),
        ExtractedQuestionOut(question='목표 달성 과정에서 발생한 문제와 그 원인을 작성해 주시기 바랍니다.', limit=400,
                             group='지어낸 상위 문항'),
    ]))
    assert result['questions'] == [
        {'question': '목표 달성 과정에서 마주한 문제를 해결한 경험 › 당시 달성해야 하는 목표는 무엇이었으며, '
                     '목표를 달성해야 하는 이유를 작성해 주시기 바랍니다.', 'limit': 400},
        # 원문에 없는 상위 문항은 붙이지 않는다
        {'question': '목표 달성 과정에서 발생한 문제와 그 원인을 작성해 주시기 바랍니다.', 'limit': 400},
    ]
