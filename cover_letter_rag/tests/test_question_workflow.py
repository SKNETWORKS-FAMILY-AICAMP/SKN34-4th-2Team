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
    assert '[앞 초안]' in calls['write'][1]['retry'] and '메모를 안 씀: 「3일 붙잡음」' in calls['write'][1]['retry']
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
