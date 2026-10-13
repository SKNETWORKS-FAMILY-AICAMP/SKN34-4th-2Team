"""Quotes the analyst corrected while citing: typo spans are accepted, paraphrases are not."""
import pytest

from app.resume_review_v2.llm import LangChainReviewLLM
from app.resume_review_v2.models import (AnalystOutput, Evidence, Experience, ExtractionOutput, ReviewInput,
                                         RevisionPlan, SpellingFix)
from app.resume_review_v2.validation import ContractError, source_quote, spelling_fixes, validate_analysis

ASPIRATION = '품질과 속도 사이의 균형을\n수치로 확인하며 맞추어 가는 일을 꿭 해 보고 싶습니다.'
CHALLENGE = '검색 결과를 하나씩 뛯어보니 임베딩은 직무가 비슷한지는 잘 잡아냈습니다.'


def test_exact_quote_is_unchanged():
    assert source_quote(CHALLENGE, '임베딩은 직무가 비슷한지는') == ('임베딩은 직무가 비슷한지는', [])


def test_quote_across_line_break_returns_source_span():
    quote, pairs = source_quote(ASPIRATION, '품질과 속도 사이의 균형을 수치로 확인하며')
    assert quote == '품질과 속도 사이의 균형을\n수치로 확인하며' and pairs == []


@pytest.mark.parametrize('source, proposed, expected_quote, expected_pairs', [
    (ASPIRATION, '맞추어 가는 일을 꼭 해 보고 싶습니다', '맞추어 가는 일을 꿭 해 보고 싶습니다', [('꿭', '꼭')]),
    (CHALLENGE, '검색 결과를 하나씩 뜯어보니 임베딩은', '검색 결과를 하나씩 뛯어보니 임베딩은', [('뛯어보니', '뜯어보니')]),
])
def test_corrected_typo_maps_back_to_source_text(source, proposed, expected_quote, expected_pairs):
    assert source_quote(source, proposed) == (expected_quote, expected_pairs)


def test_garbled_copy_of_a_rare_syllable_is_accepted_but_not_reported():
    quote, pairs = source_quote(ASPIRATION, '맞추어 가는 일을 ꭿ 해 보고 싶습니다')
    assert quote == '맞추어 가는 일을 꿭 해 보고 싶습니다' and pairs == []


@pytest.mark.parametrize('source, proposed', [
    (ASPIRATION, '맞추어 가는 일을 k 해 보고 싶습니다'),                         # a Latin letter is never a garbled syllable
    ('응답 시간을 3초까지 줄였습니다', '응답 시간을 4초까지 줄였습니다'),        # numbers are facts, not typos
    ('API를 구현했습니다 그리고 배포했습니다', 'API를 실현했습니다 그리고 배포했습니다'),  # different initial consonant
    ('가나다라마바사아자차', '가너더라마바사아자차'),                            # adjacent syllables = another word
    ('꿭 해 봅니다', '꼭 해 봅니다'),                                           # too short to locate safely
    ('일을 꿭 해 보고 그리고 일을 꿈 해 보고', '일을 꼭 해 보고'),             # two candidate spans
    ('Redis 캐시를 도입했습니다', 'Kafka 캐시를 도입했습니다'),
])
def test_paraphrase_or_ambiguous_quote_is_rejected(source, proposed):
    assert source_quote(source, proposed) == (None, [])


def _request(text):
    return ReviewInput(experience=Experience(experience_id='aspiration', kind='other', title='입사 후 포부',
        current_text=text, field_path='selfIntroduction.aspiration.body', content_hash='h'))


def _fact(quote):
    return Evidence(evidence_id='e1', experience_id='aspiration', fact_type='action', normalized_fact='균형 확인',
        evidence_quote=quote, source_type='resume_text', source_id='aspiration', assertion_state='resume_stated')


def test_validation_keeps_source_text_and_reports_the_fix():
    request = _request(ASPIRATION)
    extraction = ExtractionOutput(experience_id='aspiration', extracted_evidence=[_fact('맞추어 가는 일을 꼭 해 보고')])
    evidence, _ = validate_analysis(request, AnalystOutput(experience_id='aspiration',
        extracted_evidence=extraction.extracted_evidence, plan=RevisionPlan(objective='검증', operation='no_change')))
    assert evidence['e1'].evidence_quote == '맞추어 가는 일을 꿭 해 보고'
    assert spelling_fixes(request, extraction) == [SpellingFix(source_id='aspiration', wrong='꿭', right='꼭')]


def test_paraphrased_quote_still_fails_validation():
    request = _request(ASPIRATION)
    with pytest.raises(ContractError):
        validate_analysis(request, AnalystOutput(experience_id='aspiration',
            extracted_evidence=[_fact('맞추어 가는 일을 반드시 해 보고')], plan=RevisionPlan(objective='검증', operation='no_change')))


def _writer_payload(request):
    captured = {}
    llm = LangChainReviewLLM.__new__(LangChainReviewLLM)
    llm._call = lambda system, payload, schema: captured.update(system=system, payload=payload)
    llm.write(request, RevisionPlan(objective='다듬기', operation='replace_field'), [])
    return captured


def test_writer_gets_fixes_only_when_there_are_any():
    clean = _writer_payload(_request(ASPIRATION))
    assert 'spelling_fixes' not in clean['payload']
    fixed = _writer_payload(_request(ASPIRATION).model_copy(update={'spelling_fixes': [
        SpellingFix(source_id='aspiration', wrong='꿭', right='꼭')]}))
    assert fixed['payload']['spelling_fixes'] == [{'source_id': 'aspiration', 'wrong': '꿭', 'right': '꼭'}]
    assert 'spelling_fixes' in fixed['system']


def test_rejected_field_still_gets_typo_only_edits_that_apply_cleanly():
    from app.resume_review_runtime import spelling_reviews
    text = '공고가 꿭 좋은 추천은 아닙니다. 그래서 꿭 확인하고 싶었습니다.'
    reviews = spelling_reviews('selfIntroduction.intro.body', text,
                               [SpellingFix(source_id='intro', wrong='꿭', right='꼭')])
    assert len(reviews) == 1
    edit = reviews[0]
    assert text.count(edit.original_quote) == 1  # the apply contract replaces exactly one span
    assert edit.suggested_revision == edit.original_quote.replace('꿭', '꼭', 1)
    assert (edit.status, edit.edit_type, edit.validation_status, edit.validation_issues) == ('formatting', 'spelling', 'READY', [])


@pytest.mark.parametrize('text,intent', [
    # 2026-10-13: a student's past reason ("…가 맞다고 보고 옮겼습니다") was rejected as an unstated intent.
    ('PC 사용과 링크 공유가 불편한 앱 중심 화면을 개선하고자 React 웹을 기본으로 바꿨습니다.', False),
    ('관계형 조회가 필요해 PostgreSQL로 옮기고자 했던 이유는 중복 저장이었습니다.', False),
    ('앞으로 서비스를 총괄하고자 합니다.', True),
    ('귀사에 지원하고자 하는 이유는 데이터 품질입니다.', True),
    ('검색 품질을 더 높이고 싶습니다.', True),
])
def test_purpose_connective_on_finished_work_is_not_an_intention(text, intent):
    from app.resume_review_v2.validation import is_explicit_intention
    assert is_explicit_intention(text) is intent
