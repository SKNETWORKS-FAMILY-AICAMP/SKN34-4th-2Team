"""공고 요건 정리·근거 대조·단계 정렬. 모델은 가짜로 두고 서버가 하는 대조와 정렬만 본다."""
from app.config import Settings
from app.job_requirements import (
    JobRequirement, JobRequirementOut, JobRequirementProfileOut, ground_requirement_matches,
    load_or_extract_requirements, normalize_requirements,
)
from app.models import (
    ConfirmationAnswer, FirestoreResumeReviewRequest, RequirementMatchOut, ResumeReviewGeneration,
    ReviewQuestion, SentenceReview,
)
from app.resume_review import ResumeReviewService
from app.review_workflow import _review_stage, assign_review_stages

JOB_TEXT = """[자격요건]
- Java, Spring Boot 기반 백엔드 개발 경력 3년 이상
- Spring Boot 3.x, JDK 17 이상 사용 경험
- Git 브랜치 전략 기반 협업 경험
[우대사항]
- Redis Pub/Sub 또는 Kafka 기반 메시지 처리 경험
[근무조건]
- 정규직, 서울 송파구"""


def test_requirements_must_quote_the_posting():
    generated = JobRequirementProfileOut(requirements=[
        JobRequirementOut(group='must', label='Spring Boot 3.x', posting_quote='Spring Boot 3.x, JDK 17 이상 사용 경험'),
        JobRequirementOut(group='must', label='AWS 경험', posting_quote='AWS 기반 인프라 운영 경험'),  # 공고에 없다
        JobRequirementOut(group='preferred', label='Kafka', posting_quote='Redis Pub/Sub 또는  Kafka 기반 메시지 처리'),
        JobRequirementOut(group='must', label='spring boot 3.x', posting_quote='Spring Boot 3.x'),  # 이름 중복
    ])
    requirements = normalize_requirements(generated, JOB_TEXT)
    assert [(r.id, r.group, r.label) for r in requirements] == [
        ('req-1', 'must', 'Spring Boot 3.x'), ('req-2', 'preferred', 'Kafka'),
    ]


def test_requirements_are_extracted_once_per_posting():
    calls, store = [], {}

    class Cache:
        def get_job_requirements(self, key):
            return store.get(key)

        def save_job_requirements(self, key, value):
            store[key] = value

    def extractor(job_text, job_source):
        calls.append(job_source['job_id'])
        return JobRequirementProfileOut(requirements=[
            JobRequirementOut(group='must', label='Git 협업', posting_quote='Git 브랜치 전략 기반 협업 경험')])

    source = {'job_id': 'SARAMIN-1', 'snapshot_hash': 'abc'}
    first = load_or_extract_requirements(Cache(), extractor, JOB_TEXT, source)
    second = load_or_extract_requirements(Cache(), extractor, JOB_TEXT, source)
    assert first == second and calls == ['SARAMIN-1']


def test_met_without_verified_quote_is_downgraded():
    requirements = [
        JobRequirement(id='req-1', group='must', label='Java·Spring Boot', posting_quote='Java, Spring Boot'),
        JobRequirement(id='req-2', group='must', label='Git 협업', posting_quote='Git 브랜치 전략'),
    ]
    fields = {'coreCompetencies.text': 'Java·Spring Boot·JPA로 커머스 주문 도메인을 3년간 개발·운영.'}
    rows, warnings = ground_requirement_matches(requirements, [
        RequirementMatchOut(requirement_id='req-1', status='met',
                            evidence_quotes=['Java·Spring Boot·JPA로 커머스 주문 도메인을 3년간']),
        RequirementMatchOut(requirement_id='req-2', status='met', evidence_quotes=['Git Flow로 협업했습니다']),  # 원문에 없다
    ], fields, [])
    assert [(r.status, r.source) for r in rows] == [('met', 'resume'), ('unconfirmed', 'none')]
    assert rows[0].evidence_paths == ['coreCompetencies.text']
    assert warnings


def test_stages_follow_requirement_experience_wording_motivation_self_intro():
    assert _review_stage('projects[0].description', edit_type='clarity') == 1
    assert _review_stage('selfIntroduction.motivation.body', edit_type='clarity') == 1
    assert _review_stage('projects[0].description', 'req-1') == 2
    assert _review_stage('projects[0].description') == 3
    assert _review_stage('selfIntroduction.motivation.body') == 4
    assert _review_stage('selfIntroduction.growth.body') == 5
    generation = ResumeReviewGeneration(summary='', section_reviews=[], questions=[
        ReviewQuestion(field_path='selfIntroduction.growth.body', topic='action', question='성장?', reason='r', priority=1),
        ReviewQuestion(field_path='projects[0].description', topic='action', question='한 일?', reason='r', priority=1),
        ReviewQuestion(field_path='coreCompetencies.text', topic='scope', question='Git?', reason='r', priority=1,
                       requirement_id='req-2'),
        ReviewQuestion(field_path='coreCompetencies.text', topic='scope', question='Java?', reason='r', priority=1,
                       requirement_id='req-1'),
    ])
    rows = [{'id': 'req-1', 'status': 'met'}, {'id': 'req-2', 'status': 'unconfirmed'}]
    assign_review_stages(generation, rows)
    # 'Java?'는 모델이 이미 충족된 요건에 붙인 질문이라 요건 연결만 끊고 경험 보완(3)으로 남는다.
    assert [(q.question, q.stage) for q in generation.questions] == [
        ('Git?', 2), ('한 일?', 3), ('Java?', 3), ('성장?', 5)]


CONTENT = {
    'coreCompetencies': {'text': 'Java·Spring Boot·JPA로 커머스 주문 도메인을 3년간 개발·운영.'},
    'projects': [{'id': 'p1', 'name': '주문 조회 성능 개선', 'description': 'N+1 제거와 Redis 캐시로 조회 개선.'}],
}
JOB = {'text': JOB_TEXT, 'source': {'job_id': 'SARAMIN-1', 'company': '루멘', 'title': '백엔드',
                                    'snapshot_hash': 'h1', 'role_title': '백엔드'}}


class _Firebase:
    def __init__(self):
        self.states, self.requirements = {}, {}

    def verify_id_token(self, _):
        return 'u'

    def get_owned_tailored_resume(self, *_):
        return {'userId': 'u', 'content': CONTENT, 'jobId': 'SARAMIN-1', 'jobSnapshotHash': 'h1'}

    def claim_review(self, _c, _r, _u, request_id, fingerprint, _t=None):
        state = self.states.setdefault(request_id, {'fingerprint': fingerprint})
        return state if state.get('response') else {}

    def complete_review(self, _c, _r, _u, request_id, response, _t=None):
        self.states[request_id]['response'] = response

    def fail_review(self, *_):
        pass

    def get_ai_review(self, _c, _r, _u, review_id, _t=None):
        return self.states[review_id]['response']

    def get_job_requirements(self, key):
        return self.requirements.get(key)

    def save_job_requirements(self, key, value):
        self.requirements[key] = value


def test_none_answer_to_requirement_question_marks_it_absent(monkeypatch):
    import app.matching_handoff as handoff
    monkeypatch.setattr(handoff, 'load_selected_job', lambda _p, _j: JOB)

    def extractor(job_text, job_source):
        return JobRequirementProfileOut(requirements=[
            JobRequirementOut(group='must', label='Java·Spring Boot',
                              posting_quote='Java, Spring Boot 기반 백엔드 개발 경력 3년 이상'),
            JobRequirementOut(group='must', label='Git 협업', posting_quote='Git 브랜치 전략 기반 협업 경험'),
        ])

    def generator(_inputs):
        return ResumeReviewGeneration(summary='검토', section_reviews=[], requirement_matches=[
            RequirementMatchOut(requirement_id='req-1', status='met', evidence_quotes=['Java·Spring Boot·JPA로']),
            RequirementMatchOut(requirement_id='req-2', status='unconfirmed'),
        ], sentence_reviews=[SentenceReview(
            field_path='coreCompetencies.text', original_quote='Java·Spring Boot·JPA로 커머스 주문 도메인을 3년간 개발·운영.',
            suggested_revision='Java·Spring Boot·JPA로 커머스 주문 도메인을 3년간 개발·운영했습니다.', reason='종결',
            edit_type='clarity')])

    firebase = _Firebase()
    service = ResumeReviewService(Settings(openai_api_key='test'), firebase, generator, extractor)
    base = dict(cohort_id='c', resume_id='r', review_mode='job', tailored_resume_id='t1', selected_job_id='SARAMIN-1')
    first = service.review('x', FirestoreResumeReviewRequest(**base))
    assert [(row['label'], row['status']) for row in first.requirement_map] == [
        ('Java·Spring Boot', 'met'), ('Git 협업', 'unconfirmed')]
    question = first.questions[0]
    assert question.requirement_id == 'req-2' and question.stage == 2
    assert first.sentence_reviews[0].stage == 1

    follow = service.review('x', FirestoreResumeReviewRequest(
        **base, previous_review_id=first.review_id, expected_input_hash=first.input_hash,
        answers=[ConfirmationAnswer(question_id=question.question_id, field_path=question.field_path,
                                    question=question.question, answer='없음')]))
    assert follow.telemetry['model_skipped'] == 'none_answer'
    assert [(row['label'], row['status']) for row in follow.requirement_map] == [
        ('Java·Spring Boot', 'met'), ('Git 협업', 'absent')]
    assert all(q.requirement_id != 'req-2' for q in follow.questions)


def test_none_answer_keeps_partially_evidenced_requirement():
    # 일부 근거가 있는 요건의 질문은 "그 프로젝트에서 더 한 일"처럼 좁다. 거기에 없다고 해도
    # 이력서에 있는 근거(MQTT 전송)는 그대로다. 근거를 못 찾은 요건만 해당 없음이 된다.
    from app.job_requirements import mark_requirement_absent
    rows = [
        {'id': 'req-net', 'status': 'partial', 'source': 'resume',
         'evidence_paths': ['projects[0].description'], 'evidence_quotes': ['수집값을 MQTT로 서버에 전송']},
        {'id': 'req-avr', 'status': 'unconfirmed', 'source': 'none', 'evidence_paths': [], 'evidence_quotes': []},
    ]
    kept = mark_requirement_absent(rows, 'req-net')
    assert kept[0] == rows[0], '일부 근거가 있는 요건은 그대로 둔다'
    marked = mark_requirement_absent(rows, 'req-avr')
    assert (marked[1]['status'], marked[1]['source']) == ('absent', 'user')


def test_experience_question_linked_to_met_requirement_is_kept_unlinked():
    from app.review_workflow import REQUIREMENT_QUESTION_REASON
    generation = ResumeReviewGeneration(summary='', section_reviews=[], questions=[
        ReviewQuestion(field_path='projects[0].description', topic='action', reason='행동 부족', priority=1,
                       question='주문 조회 개선에서 직접 한 일은?', requirement_id='req-1'),
        ReviewQuestion(field_path='coreCompetencies.text', topic='scope', reason=REQUIREMENT_QUESTION_REASON, priority=1,
                       question='Java 경험이 있나요?', requirement_id='req-1'),
    ])
    assign_review_stages(generation, [{'id': 'req-1', 'status': 'met'}])
    assert [(q.question, q.requirement_id, q.stage) for q in generation.questions] == [
        ('주문 조회 개선에서 직접 한 일은?', None, 3)]


def test_requirement_questions_are_capped_must_first():
    from app.review_workflow import MAX_REQUIREMENT_QUESTIONS, REQUIREMENT_QUESTION_REASON
    rows = [{'id': f'p{i}', 'group': 'preferred', 'status': 'unconfirmed'} for i in range(3)]
    rows += [{'id': f'm{i}', 'group': 'must', 'status': 'unconfirmed'} for i in range(3)]
    questions = [ReviewQuestion(field_path='coreCompetencies.text', topic='scope', reason=REQUIREMENT_QUESTION_REASON,
                                priority=2, question=f'{row["id"]}?', requirement_id=row['id']) for row in rows]
    questions.append(ReviewQuestion(field_path='projects[0].description', topic='action', reason='모델', priority=3,
                                    question='모델 질문?', requirement_id='p2'))
    generation = ResumeReviewGeneration(summary='', section_reviews=[], questions=questions)
    assign_review_stages(generation, rows)
    linked = [q.question for q in generation.questions if q.requirement_id]
    assert len(linked) == MAX_REQUIREMENT_QUESTIONS == 4
    assert linked[:3] == ['m0?', 'm1?', 'm2?']
    assert ('모델 질문?', None, 3) in [(q.question, q.requirement_id, q.stage) for q in generation.questions]


def test_requirement_question_dropped_by_filters_is_replaced(monkeypatch):
    # 모델이 요건 질문을 이력서에 없는 칸에 붙이면 그 질문은 걸러진다. 그래도 요건 질문은 하나 남아야 한다.
    import app.matching_handoff as handoff
    monkeypatch.setattr(handoff, 'load_selected_job', lambda _p, _j: JOB)

    def extractor(job_text, job_source):
        return JobRequirementProfileOut(requirements=[
            JobRequirementOut(group='must', label='Git 협업', posting_quote='Git 브랜치 전략 기반 협업 경험')])

    def generator(_inputs):
        return ResumeReviewGeneration(summary='검토', section_reviews=[], requirement_matches=[
            RequirementMatchOut(requirement_id='req-1', status='unconfirmed')], questions=[
            ReviewQuestion(field_path='techStack[9].name', topic='scope', question='Git을 써 봤나요?', reason='r',
                           priority=1, requirement_id='req-1')])

    service = ResumeReviewService(Settings(openai_api_key='test'), _Firebase(), generator, extractor)
    first = service.review('x', FirestoreResumeReviewRequest(
        cohort_id='c', resume_id='r', review_mode='job', tailored_resume_id='t1', selected_job_id='SARAMIN-1'))
    linked = [q for q in first.questions if q.requirement_id == 'req-1']
    assert len(linked) == 1 and linked[0].field_path in first.input_fields and linked[0].question_id
