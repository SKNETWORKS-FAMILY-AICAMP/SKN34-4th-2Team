from types import SimpleNamespace

from app.job_requirements import JobRequirement
from app.question_workflow.models import (
    DraftOut, OverstatedOut, PartOut, PlanOut, QuestionInput, QuestionPlanOut, ReviewOut, SentenceOut,
)
from app.question_workflow.workflow import QuestionWorkflow, build_sources

CONTENT = {'projects': [
    {'id': 'p1', 'name': '채용공고 서비스', 'description': 'Python으로 수집 파이프라인 구현'},
    {'id': 'p2', 'name': 'LMS', 'description': 'API 연결 오류 해결'},
]}
JOB = {'text': 'Python 개발자', 'source': {'company': '가상', 'title': '백엔드'}}
REQS = [JobRequirement(id='R1', group='must', label='Python', posting_quote='Python')]


def _plan(*questions):
    return PlanOut(questions=[QuestionPlanOut(question_id=qid, parts=[PartOut(key='경험', quote='경험')],
                                              lead_source_ids=lead, angle=f'{qid} 각도') for qid, lead in questions])


def _fake(plan, drafts, reviews=None):
    drafts, reviews = list(drafts), list(reviews or [])
    calls = {'write': [], 'review': 0}

    def write(payload):
        calls['write'].append(payload)
        return drafts.pop(0)

    def review(payload):
        calls['review'] += 1
        return reviews.pop(0) if reviews else ReviewOut()

    return SimpleNamespace(plan=lambda payload: plan, write=write, review=review), calls


def _s(text, *ids, part='경험', new=False):
    return SentenceOut(text=text, source_ids=list(ids), part_key=part, new_paragraph=new)


def test_memo_pieces_are_split_and_owned_by_their_question():
    qs = [QuestionInput('q1', '문항1', memo='3일 붙잡음 / 원인은 형식\nPython·Django 공부'), QuestionInput('q2', '문항2')]
    sources = build_sources(CONTENT, qs, JOB['text'], REQS)
    memo = [s for s in sources if s.kind == 'memo']
    assert [s.text for s in memo] == ['3일 붙잡음', '원인은 형식', 'Python·Django 공부']
    assert {s.question_id for s in memo} == {'q1'}
    assert {'R1', 'R2', 'P1', 'J-R1'} <= {s.id for s in sources}


def test_clean_draft_has_no_rewrite():
    llm, calls = _fake(_plan(('q1', ['R1'])), [DraftOut(sentences=[_s('Python으로 수집 파이프라인을 구현했습니다.', 'R1')])])
    out = QuestionWorkflow(llm).run(content=CONTENT, questions=[QuestionInput('q1', '경험을 쓰시오', limit=1000)],
                                    job=JOB, requirements=REQS)
    q = out['questions'][0]
    assert q['rewrites'] == 0 and len(calls['write']) == 1
    assert q['draft'] == 'Python으로 수집 파이프라인을 구현했습니다.'
    assert q['short'] is True


def test_unsupported_number_unknown_source_and_other_memo_are_dropped_then_rewritten():
    qs = [QuestionInput('q1', '경험', memo='3일 붙잡음'), QuestionInput('q2', '경험2', memo='팀에 공유')]
    bad = DraftOut(sentences=[
        _s('API 오류를 5일 동안 붙잡았습니다.', 'M1-1'),      # 메모는 3일
        _s('팀에 공유했습니다.', 'M2-1'),                    # 다른 문항 메모
        _s('없는 재료입니다.', 'X9'),
        _s('API 연결 오류를 해결했습니다.', 'R2'),
    ])
    good = DraftOut(sentences=[_s('API 연결 오류를 3일 동안 붙잡아 해결했습니다.', 'R2', 'M1-1')])
    other = DraftOut(sentences=[_s('정리한 내용을 팀에 공유했습니다.', 'M2-1')])
    llm, calls = _fake(_plan(('q1', ['R2']), ('q2', ['R1'])), [bad, good, other])
    out = QuestionWorkflow(llm, max_workers=1).run(content=CONTENT, questions=qs, job=JOB, requirements=REQS)
    q1 = out['questions'][0]
    assert q1['rewrites'] == 1
    assert q1['draft'] == 'API 연결 오류를 3일 동안 붙잡아 해결했습니다.'
    assert '[앞 초안]' in calls['write'][1]['retry'] and '반드시 넣는다: 「3일 붙잡음」' in calls['write'][1]['retry']
    assert '[M2-1]' not in calls['write'][0]['sources']  # 남의 메모는 재료로 주지 않는다


def test_overstated_sentence_is_removed_but_answer_is_never_empty():
    draft = DraftOut(sentences=[_s('API 연결 오류를 해결했습니다.', 'R2'), _s('팀을 주도해 오류를 해결했습니다.', 'R2')])
    review = ReviewOut(overstated=[OverstatedOut(index=1, reason='주도는 근거에 없음')], questions=['어떤 역할이었나요?'])
    llm, _ = _fake(_plan(('q1', ['R2'])), [draft, draft], [review, review])
    q = QuestionWorkflow(llm).run(content=CONTENT, questions=[QuestionInput('q1', '경험', limit=500)],
                                  job=JOB, requirements=REQS)['questions'][0]
    assert q['draft'] == 'API 연결 오류를 해결했습니다.'
    assert any('주도' in r['reason'] for r in q['removed'])
    assert q['questions'] == ['어떤 역할이었나요?']


def test_limit_trims_from_the_end_and_paragraphs_join_with_newline():
    draft = DraftOut(sentences=[_s('가' * 8 + '.', 'R1'), _s('나' * 8 + '.', 'R2', new=True), _s('다' * 8 + '.', 'R1')])
    llm, _ = _fake(_plan(('q1', ['R1'])), [draft, draft])
    q = QuestionWorkflow(llm).run(content=CONTENT, questions=[QuestionInput('q1', '경험', limit=20)],
                                  job=JOB, requirements=REQS)['questions'][0]
    assert q['draft'] == '가' * 8 + '.\n' + '나' * 8 + '.'
    assert q['trimmed_for_limit'] == 1


def test_answered_note_is_not_asked_again():
    plan = PlanOut(questions=[QuestionPlanOut(question_id='q1', parts=[PartOut(key='결과', quote='결과')],
        lead_source_ids=['R2'], angle='', missing=[])])
    review = ReviewOut(questions=['결과가 어땠나요?', '무엇을 배웠나요?'])
    llm, _ = _fake(plan, [DraftOut(sentences=[_s('오류를 해결했습니다.', 'R2', 'A1-1', part='결과')])], [review])
    q = QuestionWorkflow(llm).run(content=CONTENT, job=JOB, requirements=REQS, questions=[
        QuestionInput('q1', '결과', notes=[{'question': '결과가 어땠나요?', 'answer': '오류가 다시 안 났습니다'}])])['questions'][0]
    assert q['questions'] == ['무엇을 배웠나요?']


def test_meta_sentence_about_missing_material_is_dropped():
    draft = DraftOut(sentences=[_s('반복 조회를 줄이도록 코드를 고쳤습니다.', 'R1'),
                                _s('구체적인 수치는 확인된 자료에 없어 제시하지 않겠습니다.', 'R1')])
    llm, _ = _fake(_plan(('q1', ['R1'])), [draft, draft])
    q = QuestionWorkflow(llm).run(content=CONTENT, questions=[QuestionInput('q1', '경험', limit=1000)],
                                  job=JOB, requirements=REQS)['questions'][0]
    assert q['draft'] == '반복 조회를 줄이도록 코드를 고쳤습니다.'
    assert any(r['reason'] == '글 밖의 설명' for r in q['removed'])


def test_near_duplicate_questions_are_asked_once():
    review = ReviewOut(questions=['LMS에서 직접 구현한 API 기능은 무엇인가요?', 'LMS에서 직접 구현한 API 기능은 무엇이었나요?',
                                  '결과는 어땠나요?'])
    llm, _ = _fake(_plan(('q1', ['R2'])), [DraftOut(sentences=[_s('API 연결 오류를 해결했습니다.', 'R2')])], [review])
    q = QuestionWorkflow(llm).run(content=CONTENT, questions=[QuestionInput('q1', '경험')],
                                  job=JOB, requirements=REQS)['questions'][0]
    assert q['questions'] == ['LMS에서 직접 구현한 API 기능은 무엇인가요?', '결과는 어땠나요?']


def test_sentence_asking_the_applicant_is_dropped():
    draft = DraftOut(sentences=[
        _s('develop 브랜치 병합을 맡으셨을 때 어떤 충돌이 있었는지 알려 주시면 좋겠습니다.', 'R1'),
        _s('팀원과 어떤 방식으로 조율했나요?', 'R1'),
    ])
    llm, _ = _fake(_plan(('q1', ['R1'])), [draft, draft])
    q = QuestionWorkflow(llm).run(content=CONTENT, questions=[QuestionInput('q1', '협업 경험', limit=800)],
                                  job=JOB, requirements=REQS)['questions'][0]
    assert q['draft'] == ''
    assert {r['reason'] for r in q['removed']} == {'지원자에게 묻는 말'}


def test_same_story_in_two_answers_is_kept_once_and_reported():
    from app.question_workflow.models import OverlapOut, OverlapsOut
    story = DraftOut(sentences=[_s('API 연결 오류를 해결했습니다.', 'R2')])
    other = DraftOut(sentences=[_s('Python으로 수집 파이프라인을 구현했습니다.', 'R1')])
    llm, calls = _fake(_plan(('q1', ['R2']), ('q2', ['R2'])), [story, story, other])
    seen = []

    def overlap(payload):
        seen.append(payload['answers'])
        return OverlapsOut(overlaps=[OverlapOut(story='API 오류 해결', question_ids=['q1', 'q2', 'q9'], keep='q1', reason='문제 해결 문항')])

    llm.overlap = overlap
    out = QuestionWorkflow(llm, max_workers=1).run(
        content=CONTENT, job=JOB, requirements=REQS,
        questions=[QuestionInput('q1', '문제 해결 경험'), QuestionInput('q2', '직무 역량')])
    q1, q2 = out['questions']
    assert q1['draft'] == 'API 연결 오류를 해결했습니다.' and 'trimmed_overlap' not in q1
    assert q2['draft'] == 'Python으로 수집 파이프라인을 구현했습니다.' and q2['trimmed_overlap'] == ['API 오류 해결']
    assert '「API 오류 해결」' in calls['write'][2]['retry']
    assert out['overlaps'] == [{'story': 'API 오류 해결', 'keep': 'q1', 'others': ['q2'], 'reason': '문제 해결 문항',
                                'unchanged': []}]
    assert '[q1] 문항: 문제 해결 경험' in seen[0]


def test_trimmed_answer_that_gets_too_short_keeps_the_original():
    from app.question_workflow.models import OverlapOut, OverlapsOut
    long = DraftOut(sentences=[_s('API 연결 오류를 해결했습니다.', 'R2'), _s('Python으로 수집 파이프라인을 구현했습니다.', 'R1')])
    short = DraftOut(sentences=[_s('구현했습니다.', 'R1')])
    llm, _ = _fake(_plan(('q1', ['R2']), ('q2', ['R2'])), [long, long, short])
    llm.overlap = lambda payload: OverlapsOut(overlaps=[
        OverlapOut(story='API 오류 해결', question_ids=['q1', 'q2'], keep='q1', reason='문제 해결 문항')])
    out = QuestionWorkflow(llm, max_workers=1).run(
        content=CONTENT, job=JOB, requirements=REQS,
        questions=[QuestionInput('q1', '문제 해결 경험'), QuestionInput('q2', '직무 역량')])
    q2 = out['questions'][1]
    assert q2['draft'] == 'API 연결 오류를 해결했습니다. Python으로 수집 파이프라인을 구현했습니다.'
    assert q2['overlap_unchanged'] == ['API 오류 해결'] and 'trimmed_overlap' not in q2
    assert out['overlaps'][0]['others'] == [] and out['overlaps'][0]['unchanged'] == ['q2']


def _req_s(text, *ids, reqs=()):
    return SentenceOut(text=text, source_ids=list(ids), part_key='경험', requirement_ids=list(reqs))


def test_requirement_tags_keep_only_real_posting_requirements():
    draft = DraftOut(sentences=[
        _req_s('Python으로 수집 파이프라인을 구현했습니다.', 'R1', reqs=['J-R1', 'J-X9', 'R1']),
        _req_s('공고의 Python 요건에 맞춰 준비했습니다.', 'J-R1'),  # 공고 요건을 근거로 인용 → 이름표
        _req_s('API 연결 오류를 해결했습니다.', 'R2'),
    ])
    llm, _ = _fake(_plan(('q1', ['R1'])), [draft])
    q = QuestionWorkflow(llm).run(content=CONTENT, questions=[QuestionInput('q1', '경험')],
                                  job=JOB, requirements=REQS)['questions'][0]
    assert [s['requirements'] for s in q['sentences']] == [
        [{'id': 'R1', 'label': '필수 · Python'}], [{'id': 'R1', 'label': '필수 · Python'}], []]


def test_uncovered_must_requirement_is_hint_when_in_resume_and_question_when_not():
    reqs = [JobRequirement(id='R1', group='must', label='Python', posting_quote='Python'),
            JobRequirement(id='R2', group='must', label='Kubernetes 운영', posting_quote='Kubernetes 운영 경험'),
            JobRequirement(id='R3', group='preferred', label='AWS', posting_quote='AWS'),
            JobRequirement(id='R4', group='must', label='API 연동', posting_quote='API 연동')]
    q1 = DraftOut(sentences=[_req_s('API 연결 오류를 해결했습니다.', 'R2', reqs=['J-R4'])])
    q2 = DraftOut(sentences=[_req_s('데이터로 문제를 풀고 싶습니다.', 'R1')])
    llm, _ = _fake(_plan(('q1', ['R2']), ('q2', ['R1'])), [q1, q2])
    out = QuestionWorkflow(llm, max_workers=1).run(
        content=CONTENT, job=JOB, requirements=reqs,
        questions=[QuestionInput('q1', '역량', limit=800), QuestionInput('q2', '지원 동기', limit=1000)])
    cov = out['coverage']
    assert [r['id'] for r in cov['unused_must']] == ['R1']      # 이력서에 Python 이 있다
    assert [r['id'] for r in cov['missing_must']] == ['R2']     # 이력서에 Kubernetes 가 없다
    assert {r['id']: r['covered'] for r in cov['requirements']} == {'R1': False, 'R2': False, 'R3': False, 'R4': True}
    # 요건 이름표가 있는 답(q1)에 묻는다 — 글자 수가 더 긴 지원 동기 문항이 아니라
    assert out['questions'][0]['questions'][0].startswith('공고 필수 요건 「Kubernetes 운영」')
    assert not any('Kubernetes' in x for x in out['questions'][1]['questions'])


def test_requirement_tag_without_its_key_word_in_the_sentence_is_dropped():
    reqs = [JobRequirement(id='R1', group='must', label='Python', posting_quote='Python'),
            JobRequirement(id='R2', group='must', label='LLM·RAG·벡터 검색', posting_quote='LLM, RAG, 벡터 검색'),
            JobRequirement(id='R3', group='preferred', label='품질 평가·개선', posting_quote='품질을 평가하고 개선')]
    draft = DraftOut(sentences=[
        _req_s('인터뷰로 빈자리를 확인해 LXP를 만들었습니다.', 'R1', reqs=['J-R1']),          # Python 없음 → 뗌
        _req_s('벡터 검색 결과를 규칙으로 걸렀습니다.', 'R1', reqs=['J-R2']),                 # 「벡터」 「검색」 → 둠
        _req_s('추천 결과의 문제를 찾아 품질을 개선했습니다.', 'R2', reqs=['J-R3']),            # 「품질」 「개선」 → 둠
    ])
    llm, _ = _fake(_plan(('q1', ['R1'])), [draft])
    q = QuestionWorkflow(llm).run(content=CONTENT, questions=[QuestionInput('q1', '경험')],
                                  job=JOB, requirements=reqs)['questions'][0]
    assert [[r['id'] for r in s['requirements']] for s in q['sentences']] == [[], ['R2'], ['R3']]


def test_tech_names_in_an_experience_sentence_are_tagged_even_if_the_model_forgot():
    reqs = [JobRequirement(id='R1', group='must', label='Python', posting_quote='Python'),
            JobRequirement(id='R2', group='preferred', label='LangChain/LangGraph', posting_quote='LangChain/LangGraph'),
            JobRequirement(id='R3', group='must', label='REST API', posting_quote='REST API 개발 경험')]
    draft = DraftOut(sentences=[
        _req_s('Python FastAPI로 API를 만들고 LangChain·LangGraph로 흐름을 묶었습니다.', 'R1'),  # REST 없음 → R3 아님
        _req_s('공고는 Python을 요구합니다.', 'J-R1'),  # 공고만 근거 — 코드가 더 달지 않는다(인용한 요건은 남는다)
        _req_s('Python과 LangChain을 다루는 귀사에 지원했습니다.', 'R1'),  # 회사를 향한 문장 — 경험이 아니다
    ])
    llm, _ = _fake(_plan(('q1', ['R1'])), [draft])
    q = QuestionWorkflow(llm).run(content=CONTENT, questions=[QuestionInput('q1', '경험')],
                                  job=JOB, requirements=reqs)['questions'][0]
    assert [[r['id'] for r in s['requirements']] for s in q['sentences']] == [['R1', 'R2'], ['R1'], []]


def test_tag_pass_adds_grounded_tags_and_feeds_coverage():
    from app.question_workflow.models import SentenceTagOut, TagEvidenceOut, TagsOut
    reqs = [JobRequirement(id='R1', group='must', label='품질 평가·개선', posting_quote='품질을 평가하고 개선'),
            JobRequirement(id='R2', group='must', label='Python', posting_quote='Python')]
    draft = DraftOut(sentences=[
        _req_s('검증 점수가 무너지자 Voting으로 바꿨습니다.', 'R1'),
        _req_s('API 연결 오류를 해결했습니다.', 'R2'),
        _req_s('품질을 중시하는 귀사에 지원했습니다.', 'R1'),
    ])
    llm, _ = _fake(_plan(('q1', ['R1'])), [draft])
    llm.tag = lambda payload: TagsOut(sentences=[
        SentenceTagOut(index=0, tags=[TagEvidenceOut(requirement_id='R1', evidence='검증 점수가 무너지자 Voting으로 바꿨')]),
        SentenceTagOut(index=1, tags=[TagEvidenceOut(requirement_id='R2', evidence='Python으로 고쳤습니다'),   # 문장에 없음
                                      TagEvidenceOut(requirement_id='R9', evidence='API')]),               # 없는 요건
        SentenceTagOut(index=2, tags=[TagEvidenceOut(requirement_id='J-R1', evidence='품질을 중시하는')]),  # 회사를 향한 문장
        SentenceTagOut(index=7, tags=[TagEvidenceOut(requirement_id='R1', evidence='x')]),
    ])
    out = QuestionWorkflow(llm).run(content=CONTENT, questions=[QuestionInput('q1', '실패 경험')],
                                    job=JOB, requirements=reqs)
    sentences = out['questions'][0]['sentences']
    assert [[r['id'] for r in s['requirements']] for s in sentences] == [['R1'], [], []]
    assert sentences[0]['requirement_evidence'] == {'R1': '검증 점수가 무너지자 Voting으로 바꿨'}
    assert {r['id']: r['covered'] for r in out['coverage']['requirements']} == {'R1': True, 'R2': False}


def test_posting_is_split_into_lines_so_quotes_stay_short():
    job_text = '가상 기업 채용\n\n인재상\n- 근거로 말하는 사람\n회사 소개: 기업 문서 검색 서비스를 만듭니다'
    sources = build_sources(CONTENT, [QuestionInput('q1', '지원 동기')], job_text, [])
    posting = [(s.id, s.text) for s in sources if s.kind == 'posting']
    assert posting == [('P1', '가상 기업 채용'), ('P2', '인재상'), ('P3', '- 근거로 말하는 사람'),
                       ('P4', '회사 소개: 기업 문서 검색 서비스를 만듭니다')]


def test_only_one_question_reuses_saved_plan_and_skips_set_steps():
    first = DraftOut(sentences=[_s('API 연결 오류를 해결했습니다.', 'R2')])
    calls = {'plan': 0}
    llm, writes = _fake(_plan(('q1', ['R2']), ('q2', ['R1'])), [first])

    def plan(payload):
        calls['plan'] += 1
        return _plan(('q1', ['R2']), ('q2', ['R1']))

    llm.plan = plan
    llm.overlap = lambda payload: (_ for _ in ()).throw(AssertionError('한 문항일 때는 겹침 검토를 하지 않는다'))
    saved = {'q1': _plan(('q1', ['R2'])).questions[0].model_dump(), 'q2': _plan(('q2', ['R1'])).questions[0].model_dump()}
    qs = [QuestionInput('q1', '문제 해결'), QuestionInput('q2', '역량')]
    out = QuestionWorkflow(llm).run(content=CONTENT, questions=qs, job=JOB, requirements=REQS, only='q1', saved_plan=saved)
    assert calls['plan'] == 0 and len(writes['write']) == 1
    assert [q['question_id'] for q in out['questions']] == ['q1'] and out['only'] == 'q1'
    assert out['coverage'] is None and out['overlaps'] == []
    assert 'q2: 역량' not in writes['write'][0]['question']  # 쓰는 건 q1 하나


def test_only_with_broken_or_missing_plan_replans_and_unknown_question_is_rejected():
    import pytest
    from app.review_workflow import ReviewInputError
    llm, _ = _fake(_plan(('q1', ['R2'])), [DraftOut(sentences=[_s('API 연결 오류를 해결했습니다.', 'R2')])])
    qs = [QuestionInput('q1', '문제 해결')]
    out = QuestionWorkflow(llm).run(content=CONTENT, questions=qs, job=JOB, requirements=REQS,
                                    only='q1', saved_plan={'q1': {'nonsense': True}})
    assert out['questions'][0]['draft'] == 'API 연결 오류를 해결했습니다.'
    with pytest.raises(ReviewInputError):
        QuestionWorkflow(llm).run(content=CONTENT, questions=qs, job=JOB, requirements=REQS, only='q9')


def test_short_answer_with_unused_lead_material_is_filled_from_that_material():
    # 예시 이력서 재료: R1 채용공고 서비스(이름) · R2 Python 파이프라인 · R3 LMS(이름) · R4 API 연결 오류 해결
    plan = PlanOut(questions=[QuestionPlanOut(question_id='q1', parts=[PartOut(key='경험', quote='경험')],
                                              lead_source_ids=['R2', 'R4'], angle='')])
    short = DraftOut(sentences=[_s('Python으로 수집 파이프라인을 구현했습니다.', 'R2')])
    longer = DraftOut(sentences=[_s('Python으로 수집 파이프라인을 구현했습니다.', 'R2'),
                                 _s('API 연결 오류도 원인을 찾아 해결했습니다.', 'R4')])
    llm, calls = _fake(plan, [short, longer])
    q = QuestionWorkflow(llm).run(content=CONTENT, questions=[QuestionInput('q1', '경험', limit=200)],
                                  job=JOB, requirements=REQS)['questions'][0]
    assert q['rewrites'] == 1
    assert '지금 이야기와 같은 사건의 것으로만' in calls['write'][1]['retry'] and '[R4] API 연결 오류 해결' in calls['write'][1]['retry']
    assert q['draft'].endswith('API 연결 오류도 원인을 찾아 해결했습니다.')


def test_short_answer_without_unused_material_is_not_rewritten_for_length():
    llm, calls = _fake(_plan(('q1', ['R2'])), [DraftOut(sentences=[_s('Python으로 수집 파이프라인을 구현했습니다.', 'R2')])])
    q = QuestionWorkflow(llm).run(content=CONTENT, questions=[QuestionInput('q1', '경험', limit=1000)],
                                  job=JOB, requirements=REQS)['questions'][0]
    assert q['rewrites'] == 0 and len(calls['write']) == 1


def test_dense_sentence_is_split_on_rewrite():
    dense = ('채용공고 서비스에서 Python으로 공고를 모으고 사이트마다 다른 형식을 맞추고 중복 공고를 지우고 조회용 API를 만들고 '
             '조회 흐름을 고쳐 반복 조회를 줄이며 운영까지 맡아 모은 데이터를 실제 서비스로 이어 주는 일을 처음부터 끝까지 해냈습니다.')
    assert len(dense) > 120
    first = DraftOut(sentences=[_s(dense, 'R2')])
    split = DraftOut(sentences=[_s('채용공고 서비스에서 Python으로 수집 파이프라인을 만들었습니다.', 'R2'),
                                _s('조회 흐름을 고쳐 반복 조회를 줄였습니다.', 'R2')])
    llm, calls = _fake(_plan(('q1', ['R2'])), [first, split])
    q = QuestionWorkflow(llm).run(content=CONTENT, questions=[QuestionInput('q1', '경험', limit=300)],
                                  job=JOB, requirements=REQS)['questions'][0]
    assert q['rewrites'] == 1 and '빽빽한 문장' in calls['write'][1]['retry']
    assert len(q['sentences']) == 2


RESULT_CONTENT = {'projects': [
    {'id': 'p1', 'name': '추천', 'description': '조건 필터를 넣어 상관계수가 +0.26에서 +0.42로 올랐다'},
]}


def test_missing_before_after_result_from_cited_material_triggers_rewrite():
    # 재료: R1 추천(이름) · R2 「…+0.26에서 +0.42로 올랐다」
    first = DraftOut(sentences=[_s('조건 필터를 넣어 추천을 고쳤습니다.', 'R2')])
    second = DraftOut(sentences=[_s('조건 필터를 넣어 상관계수가 0.26에서 0.42로 올랐습니다.', 'R2')])
    llm, calls = _fake(_plan(('q1', ['R2'])), [first, second])
    q = QuestionWorkflow(llm).run(content=RESULT_CONTENT, questions=[QuestionInput('q1', '역량', limit=100)],
                                  job=JOB, requirements=[])['questions'][0]
    assert q['rewrites'] == 1 and '개선 전후 결과를 빠뜨림' in calls['write'][1]['retry']
    assert '0.42' in q['draft']


def test_result_check_is_skipped_when_trimming_an_overlapping_story():
    from app.question_workflow.models import OverlapOut, OverlapsOut
    full = DraftOut(sentences=[_s('조건 필터를 넣어 상관계수가 0.26에서 0.42로 올랐습니다.', 'R2')])
    trimmed = DraftOut(sentences=[_s('조건 필터를 넣어 추천을 고쳤습니다.', 'R2')])
    llm, calls = _fake(_plan(('q1', ['R2']), ('q2', ['R2'])), [full, full, trimmed])
    llm.overlap = lambda payload: OverlapsOut(overlaps=[
        OverlapOut(story='추천 개선', question_ids=['q1', 'q2'], keep='q1', reason='')])
    out = QuestionWorkflow(llm, max_workers=1).run(
        content=RESULT_CONTENT, job=JOB, requirements=[],
        questions=[QuestionInput('q1', '역량', limit=100), QuestionInput('q2', '지원 동기', limit=60)])
    assert len(calls['write']) == 3  # 줄여 쓴 q2 는 결과 누락으로 다시 쓰지 않는다
    assert out['questions'][1]['draft'] == '조건 필터를 넣어 추천을 고쳤습니다.'


GOAL = '목표 달성 과정에서 마주한 문제를 해결한 경험'


def test_sub_questions_of_one_group_are_written_in_order_with_the_previous_answer():
    first = DraftOut(sentences=[_s('API 연결 오류를 해결하는 것이 목표였습니다.', 'R4')])
    second = DraftOut(sentences=[_s('원인은 요청 형식이었고 형식을 맞춰 해결했습니다.', 'R4')])
    seen = {}
    llm, calls = _fake(_plan(('q1', ['R4']), ('q2', ['R4'])), [first, second])
    plan_fn = llm.plan
    llm.plan = lambda payload: (seen.setdefault('plan', payload), plan_fn(payload))[1]
    qs = [QuestionInput('q1', f'{GOAL} › 목표는 무엇이었나요'),            # 예전 저장 모양
          QuestionInput('q2', '문제와 해결 방법은 무엇이었나요', group=GOAL)]  # 새 저장 모양
    out = QuestionWorkflow(llm).run(content=CONTENT, questions=qs, job=JOB, requirements=REQS)
    assert f'q1 [묶음: {GOAL}]' in seen['plan']['questions'] and f'q2 [묶음: {GOAL}]' in seen['plan']['questions']
    assert calls['write'][0]['siblings'] == '없음'
    assert calls['write'][1]['siblings'] == 'API 연결 오류를 해결하는 것이 목표였습니다.'
    assert calls['write'][1]['question'] == f'{GOAL} › 문제와 해결 방법은 무엇이었나요'
    assert [q['question_id'] for q in out['questions']] == ['q1', 'q2']


def test_overlap_inside_one_group_is_not_trimmed_but_other_groups_are():
    from app.question_workflow.models import OverlapOut, OverlapsOut
    d = DraftOut(sentences=[_s('API 연결 오류를 해결했습니다.', 'R4')])
    short = DraftOut(sentences=[_s('Python으로 수집 파이프라인을 구현했고, 그 과정을 정리했습니다.', 'R2')])
    llm, calls = _fake(_plan(('q1', ['R4']), ('q2', ['R4']), ('q3', ['R4'])), [d, d, d, short])
    llm.overlap = lambda payload: OverlapsOut(overlaps=[
        OverlapOut(story='API 오류', question_ids=['q1', 'q2'], keep='q1', reason=''),          # 같은 묶음 — 무시
        OverlapOut(story='API 오류', question_ids=['q1', 'q2', 'q3'], keep='q2', reason='')])   # q3 만 줄인다
    qs = [QuestionInput('q1', 'a', group=GOAL), QuestionInput('q2', 'b', group=GOAL), QuestionInput('q3', '지원 동기')]
    out = QuestionWorkflow(llm, max_workers=1).run(content=CONTENT, questions=qs, job=JOB, requirements=REQS)
    assert [(o['keep'], o['others']) for o in out['overlaps']] == [('q2', ['q3'])]
    assert out['questions'][2]['trimmed_overlap'] == ['API 오류'] and 'trimmed_overlap' not in out['questions'][0]


def test_single_question_rewrite_in_a_group_rewrites_the_whole_group_in_order():
    first = DraftOut(sentences=[_s('API 연결 오류를 해결하는 것이 목표였습니다.', 'R4')])
    second = DraftOut(sentences=[_s('형식을 맞춰 해결했습니다.', 'R4')])
    llm, calls = _fake(_plan(('q1', ['R4']), ('q2', ['R4']), ('q3', ['R2'])), [first, second])
    qs = [QuestionInput('q1', '목표', group=GOAL), QuestionInput('q2', '해결', group=GOAL),
          QuestionInput('q3', '지원 동기')]
    out = QuestionWorkflow(llm).run(content=CONTENT, questions=qs, job=JOB, requirements=REQS, only='q2')
    assert [q['question_id'] for q in out['questions']] == ['q1', 'q2']  # 묶음 전체, 다른 문항(q3)은 그대로
    assert calls['write'][1]['siblings'] == 'API 연결 오류를 해결하는 것이 목표였습니다.'


CONFLICT = '조직 내에서 갈등이 발생했으나 상대를 설득하여 갈등을 해결한 경험'


def test_answer_given_on_one_sub_question_is_material_for_its_group_sibling():
    d = DraftOut(sentences=[_s('API 연결 오류를 해결했습니다.', 'R4')])
    llm, calls = _fake(_plan(('q1', ['R4']), ('q2', ['R4'])), [d, d])
    qs = [QuestionInput('q1', '각자의 입장', group=CONFLICT,
                        notes=[{'question': '의견이 달랐던 적은?', 'answer': '응답 형식을 두고 프론트 팀원과 의견이 달랐습니다'}]),
          QuestionInput('q2', '설득 전략', group=CONFLICT)]
    QuestionWorkflow(llm, max_workers=1).run(content=CONTENT, questions=qs, job=JOB, requirements=REQS)
    assert '[A1-1]' in calls['write'][1]['sources']  # q1 에 한 답을 q2 도 근거로 받는다
    assert calls['write'][1]['memo'] == '없음'          # 남의 메모 · 답은 「꼭 쓸 메모」가 아니다


def test_questions_of_an_all_empty_group_are_gathered_on_the_first_sub_question():
    from app.question_workflow.models import MissingOut
    plan = PlanOut(questions=[
        QuestionPlanOut(question_id='q1', parts=[PartOut(key='입장', quote='입장')], lead_source_ids=[], angle='',
                        missing=[MissingOut(part_key='입장', question='LMS 프로젝트에서 팀원과 의견이 달랐던 적이 있나요?')]),
        QuestionPlanOut(question_id='q2', parts=[PartOut(key='설득', quote='설득')], lead_source_ids=[], angle='',
                        missing=[MissingOut(part_key='설득', question='그때 상대를 어떻게 설득했고 결과는 어땠나요?')]),
    ])
    llm, _ = _fake(plan, [DraftOut(sentences=[])] * 4)  # 빈 초안은 한 번 더 고쳐 쓴다
    qs = [QuestionInput('q1', '각자의 입장', group=CONFLICT), QuestionInput('q2', '설득 전략', group=CONFLICT)]
    q1, q2 = QuestionWorkflow(llm, max_workers=1).run(content=CONTENT, questions=qs, job=JOB, requirements=REQS)['questions']
    assert q1['questions'] == ['LMS 프로젝트에서 팀원과 의견이 달랐던 적이 있나요?', '그때 상대를 어떻게 설득했고 결과는 어땠나요?']
    assert q2['questions'] == [] and q2['questions_on'] == 'q1'


def test_writing_one_question_shows_what_other_questions_already_wrote():
    llm, calls = _fake(_plan(('q1', ['R4']), ('q2', ['R2'])), [DraftOut(sentences=[_s('Python으로 수집 파이프라인을 구현했습니다.', 'R2')])])
    qs = [QuestionInput('q1', '문제 해결', written='API 연결 오류를 3일 추적해 해결했습니다.'), QuestionInput('q2', '직무 역량')]
    QuestionWorkflow(llm).run(content=CONTENT, questions=qs, job=JOB, requirements=REQS, only='q2')
    assert '이미 쓴 답: API 연결 오류를 3일 추적해 해결했습니다.' in calls['write'][0]['others']


def test_questions_asking_the_same_thing_in_different_words_are_merged():
    from app.question_workflow.workflow import _same_question
    assert _same_question('학창시절 친구들과 어떤 관계를 맺었고, 그 관계에서 기억에 남는 구체적인 경험이나 배운 점이 있나요?',
                          '학창 시절 친구들과 지내며 기억에 남는 경험이나 관계가 있었나요?')
    assert not _same_question('학창시절 친구들과 어떤 관계를 맺었나요?', '성장 과정에서 크게 영향을 받은 사건이 있다면 알려 주세요.')


def test_two_digit_year_in_memo_supports_four_digit_year_in_answer():
    d = DraftOut(sentences=[_s('1996년 화목한 가정에서 누나와 함께 자랐습니다.', 'M1-1')])
    llm, _ = _fake(_plan(('q1', [])), [d])
    q = QuestionWorkflow(llm).run(content=CONTENT, job=JOB, requirements=REQS,
                                  questions=[QuestionInput('q1', '성장과정', memo='96년 화목한 집안 누나 있음')])['questions'][0]
    assert q['draft'] == '1996년 화목한 가정에서 누나와 함께 자랐습니다.' and q['removed'] == []


def test_memo_only_in_overstated_sentence_counts_as_lost_and_clean_rewrite_wins():
    # 메모를 쓴 문장이 근거보다 세서 빠지면 메모도 사라진다 — 그 초안은 메모를 안 쓴 것으로 치고 다시 쓴다
    q = QuestionInput('q1', '성장과정', limit=500, memo='화목한 집안 / 긍정적인 생활습관')
    bad = DraftOut(sentences=[_s('화목한 가정에서 자라며 긍정적인 태도를 갖게 됐습니다.', 'M1-1', 'M1-2'),
                              _s('Python으로 수집 파이프라인을 구현했습니다.', 'R1')])
    good = DraftOut(sentences=[_s('화목한 가정에서 자랐습니다.', 'M1-1'), _s('긍정적인 생활습관을 지켜 왔습니다.', 'M1-2')])
    over = ReviewOut(overstated=[OverstatedOut(index=0, reason='인과를 지어냄')])
    llm, calls = _fake(_plan(('q1', [])), [bad, good], [over, ReviewOut()])
    out = QuestionWorkflow(llm).run(content=CONTENT, job=JOB, requirements=REQS, questions=[q])['questions'][0]
    assert '세서 빠짐' in calls['write'][1]['retry'] and '「화목한 집안」' in calls['write'][1]['retry']
    assert out['draft'] == '화목한 가정에서 자랐습니다. 긍정적인 생활습관을 지켜 왔습니다.'


def test_listed_items_in_question_become_parts_even_if_plan_collapses_them():
    # 계획이 「가족사항」 하나로 묶어도 문항이 늘어놓은 것은 모두 요구가 된다 — 검토가 빠진 요구로 잡는다
    q = QuestionInput('q1', '성장과정:가족사항, 학창시절, 교우관계, 영향을 미친 사건 등을 포함하여 작성', limit=500)
    plan = PlanOut(questions=[QuestionPlanOut(question_id='q1', parts=[PartOut(key='가족사항', quote='가족사항')],
                                              lead_source_ids=[], angle='가족')])
    llm, calls = _fake(plan, [DraftOut(sentences=[_s('Python으로 수집 파이프라인을 구현했습니다.', 'R1', part='가족사항')])])
    reviews = []
    llm.review = lambda payload: reviews.append(payload) or ReviewOut()
    out = QuestionWorkflow(llm).run(content=CONTENT, job=JOB, requirements=REQS, questions=[q])['questions'][0]
    assert out['parts'] == ['가족사항', '학창시절', '교우관계', '영향을 미친 사건']
    assert reviews[0]['parts'] == '가족사항, 학창시절, 교우관계, 영향을 미친 사건'


def test_keyboard_mash_memo_is_not_material():
    # 「ㄴ이ㅏㅓㅁㄴㅇ」을 메모로 꼭 쓰라고 하면 「메모에는 ‘ㄴ이ㅏㅓㅁㄴㅇ’이라고 적었습니다」가 나온다
    qs = [QuestionInput('q1', '문항1', memo='ㄴ이ㅏㅓㅁㄴㅇ / 팀장 ㅠㅠ 설득함')]
    memo = [s.text for s in build_sources(CONTENT, qs, JOB['text'], REQS) if s.kind == 'memo']
    assert memo == ['팀장 설득함']


def test_dotted_resume_date_supports_korean_date_in_answer():
    # 이력서 「2015.03」은 숫자 검사에서 소수 2015.03 이 된다 — 「2015년 3월부터」 학력 문장이 통째로 빠졌다
    content = {'education': [{'school': '수원과학대학교', 'major': '실용음악과', 'startDate': '2015.03', 'endDate': '2017.02'}]}
    sources = build_sources(content, [QuestionInput('q1', '성장과정')], '', [])
    ids = [s.id for s in sources if s.kind == 'resume' and s.text in ('2015.03', '2017.02', '실용음악과')]
    d = DraftOut(sentences=[_s('2015년 3월부터 2017년 2월까지 실용음악과를 다녔습니다.', *ids)])
    llm, _ = _fake(_plan(('q1', [])), [d])
    q = QuestionWorkflow(llm).run(content=content, job=JOB, requirements=[],
                                  questions=[QuestionInput('q1', '성장과정')])['questions'][0]
    assert q['removed'] == [] and q['draft'].startswith('2015년 3월부터')


def test_empty_plan_entry_is_planned_again_and_only_the_empty_one_is_filled():
    # 계획이 문항 하나를 각도 · 재료 없이 돌려주면 한 번 더 세워 그 문항만 채운다
    empty = PlanOut(questions=[QuestionPlanOut(question_id='q1', parts=[PartOut(key='가족사항', quote='가족사항')],
                                               lead_source_ids=[], angle='')])
    good = _plan(('q1', ['R1']), ('q2', ['R2']))
    plans = [empty, good]
    d = DraftOut(sentences=[_s('Python으로 수집 파이프라인을 구현했습니다.', 'R1')])
    llm, _ = _fake(None, [d, d])
    llm.plan = lambda payload: plans.pop(0)
    out = QuestionWorkflow(llm).run(content=CONTENT, job=JOB, requirements=REQS,
                                    questions=[QuestionInput('q1', '문항1'), QuestionInput('q2', '문항2')])
    assert out['plan']['q1']['angle'] == 'q1 각도' and out['plan']['q1']['lead_source_ids'] == ['R1']
    assert out['plan']['q2']['lead_source_ids'] == ['R2'] and plans == []


def test_citing_school_brings_dates_of_the_same_education_entry():
    # 학교 · 전공만 근거로 달아도 같은 학력 항목의 입학 · 졸업 날짜를 근거로 본다 — 숫자 검사 · 검토 모두
    content = {'education': [{'school': '수원과학대학교', 'major': '실용음악과', 'startDate': '2015.03', 'endDate': '2017.02'},
                             {'school': '한양사이버대학교', 'major': '응용소프트웨어학과', 'endDate': '2026.02'}]}
    d = DraftOut(sentences=[_s('2017년 수원과학대학교 실용음악과를 졸업했습니다.', 'R1', 'R2')])
    llm, _ = _fake(_plan(('q1', [])), [d])
    reviews = []
    llm.review = lambda payload: reviews.append(payload) or ReviewOut()
    q = QuestionWorkflow(llm).run(content=content, job=JOB, requirements=[],
                                  questions=[QuestionInput('q1', '성장과정')])['questions'][0]
    assert q['removed'] == []
    assert '2017.02' in reviews[0]['sentences'] and '2026.02' not in reviews[0]['sentences']


def test_outline_reaches_writer_and_empty_beats_become_questions():
    # 문항 문구에서 세운 뼈대를 쓰기에 넘기고, 재료 없는 대목은 학생에게 묻는다
    from app.question_workflow.models import BeatOut
    plan = PlanOut(questions=[QuestionPlanOut(
        question_id='q1', parts=[PartOut(key='실패', quote='실패'), PartOut(key='교훈', quote='교훈')],
        checks=['원인을 어떻게 찾았나', '교훈이 행동으로 이어졌나'],
        outline=[BeatOut(point='수집이 막힘', part_key='실패', source_ids=['R1']),
                 BeatOut(point='원인을 찾은 과정', part_key='실패', question='처음 무엇을 의심했나요?'),
                 BeatOut(point='그 뒤 바꾼 습관', part_key='교훈', source_ids=['ZZ'], question='그 뒤 무엇을 다르게 하나요?')],
        lead_source_ids=[], angle='실패를 인정하고 고친 과정')])
    d = DraftOut(sentences=[_s('Python 수집 파이프라인이 막혔습니다.', 'R1', part='실패')])
    llm, calls = _fake(plan, [d, d])
    out = QuestionWorkflow(llm).run(content=CONTENT, job=JOB, requirements=REQS,
                                    questions=[QuestionInput('q1', '실패와 교훈', limit=300)])
    w = calls['write'][0]
    assert '1. 수집이 막힘 (실패) — 재료: R1' in w['outline'] and '2. 원인을 찾은 과정 (실패) — 재료 없음' in w['outline']
    assert '3. 그 뒤 바꾼 습관 (교훈) — 재료 없음' in w['outline']  # 없는 id 는 지운다
    assert w['checks'] == '원인을 어떻게 찾았나 / 교훈이 행동으로 이어졌나'
    assert out['plan']['q1']['lead_source_ids'] == ['R1']
    assert out['questions'][0]['questions'][:2] == ['처음 무엇을 의심했나요?', '그 뒤 무엇을 다르게 하나요?']


def _polish_case(edited, grounded):
    q = QuestionInput('q1', '경험', limit=500, memo='3일 붙잡음')
    d = DraftOut(sentences=[_s('3일 동안 API 연결 오류를 붙잡았습니다.', 'M1-1', 'R2'), _s('Python으로 수집 파이프라인을 구현했습니다.', 'R1')])
    llm, _ = _fake(_plan(('q1', ['R2'])), [d])
    llm.edit = lambda payload: edited
    llm.ground = lambda payload: grounded
    return QuestionWorkflow(llm).run(content=CONTENT, job=JOB, requirements=REQS, questions=[q])['questions'][0]


def test_polished_draft_replaces_draft_when_facts_hold():
    text = 'API 연결 오류를 3일 동안 붙잡았고, 그 과정에서 Python 수집 파이프라인을 구현했습니다.'
    out = _polish_case(text, DraftOut(sentences=[_s(text, 'M1-1', 'R2', 'R1')]))
    assert out['draft'] == text


def test_polished_draft_with_new_number_or_lost_memo_is_thrown_away():
    original = '3일 동안 API 연결 오류를 붙잡았습니다. Python으로 수집 파이프라인을 구현했습니다.'
    added = 'API 연결 오류를 3일 동안 붙잡아 응답을 5배 빠르게 했고, Python 수집 파이프라인을 구현했습니다.'
    assert _polish_case(added, DraftOut(sentences=[_s(added, 'M1-1', 'R2', 'R1')]))['draft'] == original
    no_memo = 'API 연결 오류를 끝까지 붙잡았고, 그 과정에서 Python 수집 파이프라인을 구현했습니다.'
    assert _polish_case(no_memo, DraftOut(sentences=[_s(no_memo, 'R2', 'R1')]))['draft'] == original


def test_answered_beat_in_saved_plan_uses_the_answer_instead_of_skipping():
    # 처음 계획을 그대로 다시 보내도, 학생이 답한 대목은 「재료 없음」이 아니라 그 답을 재료로 쓴다
    from app.question_workflow.models import BeatOut
    saved = QuestionPlanOut(
        question_id='q1', parts=[PartOut(key='실패', quote='실패')], lead_source_ids=['R2'], angle='각도',
        outline=[BeatOut(point='막힌 상황', part_key='실패', source_ids=['R2']),
                 BeatOut(point='원인을 찾은 과정', part_key='실패', question='처음 무엇을 의심했고 어떻게 확인했나요?')])
    q = QuestionInput('q1', '실패', limit=300,
                      notes=[{'question': '처음 무엇을 의심했고 어떻게 확인했나요?', 'answer': 'fold별 점수를 비교함'}])
    d = DraftOut(sentences=[_s('API 연결 오류가 났습니다.', 'R2', part='실패'), _s('fold별 점수를 비교했습니다.', 'A1-1', part='실패')])
    llm, calls = _fake(None, [d, d])
    out = QuestionWorkflow(llm).run(content=CONTENT, job=JOB, requirements=REQS, questions=[q],
                                    only='q1', saved_plan={'q1': saved.model_dump()})
    assert '2. 원인을 찾은 과정 (실패) — 재료: A1-1' in calls['write'][0]['outline']
    assert out['questions'][0]['questions'] == []


def test_plan_stage_returns_plan_only_without_writing():
    # 문항 전체를 여러 요청에 나눌 때 첫 요청 — 계획만(한 요청이 nginx 210초를 넘지 않게)
    llm, calls = _fake(_plan(('q1', ['R1']), ('q2', ['R2'])), [])
    out = QuestionWorkflow(llm).run(content=CONTENT, job=JOB, requirements=REQS, stage='plan',
                                    questions=[QuestionInput('q1', '문항1'), QuestionInput('q2', '문항2')])
    assert out['stage'] == 'plan' and out['questions'] == [] and set(out['plan']) == {'q1', 'q2'}
    assert calls['write'] == [] and calls['review'] == 0


def test_finish_stage_checks_the_set_from_given_answers_without_writing_again():
    # 마지막 요청 — 문항별로 받은 답으로 겹침 · 필수 요건만 본다. 겹침이 없으면 쓰기를 다시 하지 않는다
    from app.question_workflow.models import OverlapsOut
    plan = _plan(('q1', ['R1']), ('q2', ['R2']))
    llm, calls = _fake(plan, [])
    llm.overlap = lambda payload: OverlapsOut(overlaps=[])
    answers = {
        'q1': {'draft': 'Python으로 수집 파이프라인을 구현했습니다.', 'questions': ['더 알려 주세요?'],
               'sentences': [{'text': 'Python으로 수집 파이프라인을 구현했습니다.', 'source_ids': ['R1'],
                              'requirement_ids': ['J-R1', 'J-가짜']}]},
        'q2': {'draft': 'API 연결 오류를 해결했습니다.', 'sentences': [{'text': 'API 연결 오류를 해결했습니다.', 'source_ids': ['R2']}]},
    }
    out = QuestionWorkflow(llm).run(content=CONTENT, job=JOB, requirements=REQS, stage='finish', answers=answers,
                                    saved_plan={p.question_id: p.model_dump() for p in plan.questions},
                                    questions=[QuestionInput('q1', '문항1'), QuestionInput('q2', '문항2')])
    assert out['stage'] == 'finish' and calls['write'] == []
    a1 = out['questions'][0]
    assert a1['sentences'][0]['requirement_ids'] == ['J-R1']  # 공고에 없는 이름표는 버린다
    assert out['coverage']['requirements'][0]['covered'] is True


def test_finish_stage_without_answers_is_an_input_error():
    import pytest
    from app.review_workflow import ReviewInputError
    llm, _ = _fake(_plan(('q1', [])), [])
    with pytest.raises(ReviewInputError):
        QuestionWorkflow(llm).run(content=CONTENT, job=JOB, requirements=REQS, stage='finish', answers={},
                                  questions=[QuestionInput('q1', '문항1')])
