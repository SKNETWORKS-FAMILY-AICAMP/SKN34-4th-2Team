"""LangSmith 추적의 개인정보 가리기."""

from langsmith import Client
from langsmith.anonymizer import create_anonymizer

from app.trace_privacy import mask_value


def test_글_속_연락처_주민번호_개인링크_이름을_가린다():
    text = (
        '이름: 문성호\n연락처 010-2550-3171, 02-123-4567 / 이메일 moon.sh@naver.com\n'
        '주민번호 990619-1234567 · 깃허브 https://github.com/moonsh/lms · 블로그 https://moonsh.tistory.com/12'
    )
    masked = mask_value(text, [])
    assert '문성호' not in masked and '이름: [이름]' in masked
    assert '010-2550-3171' not in masked and '02-123-4567' not in masked
    assert 'moon.sh@naver.com' not in masked
    assert '990619-1234567' not in masked
    assert 'github.com/moonsh' not in masked and 'tistory' not in masked
    assert masked.count('[전화번호]') == 2


def test_날짜_수치_기술_이름은_그대로_둔다():
    text = '2025-03 ~ 2025-09 · 응답 1,200ms → 300ms · Python 3.12 · 학번 20211234 · 버전 1.0.2'
    assert mask_value(text, []) == text


def test_기본정보와_학생_이름_칸만_통째로_가린다():
    assert mask_value('문성호', ['resume', 'basicInfo', 'name']) == '[가림]'
    assert mask_value('문성호', ['student', 'displayName']) == '[가림]'
    # 프로젝트 · 기술 이름은 그대로
    assert mask_value('수강생 LMS 챗봇', ['projects', 0, 'name']) == '수강생 LMS 챗봇'
    assert mask_value('Python', ['techStack', 0, 'name']) == 'Python'


def test_LangSmith_클라이언트가_보내기_전에_가린다():
    client = Client(api_key='test', anonymizer=create_anonymizer(mask_value), auto_batch_tracing=False)
    sent = client._hide_run_inputs(  # noqa: SLF001 — 보내기 직전 입력에 걸리는 처리
        {'messages': [{'content': '저는 문성호(010-1111-2222)입니다.'}], 'basicInfo': {'name': '문성호'}}
    )
    assert sent['basicInfo']['name'] == '[가림]'
    assert '010-1111-2222' not in sent['messages'][0]['content']
