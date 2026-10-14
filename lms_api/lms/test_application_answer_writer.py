"""Local test DB only; no external LLM calls or production routing."""
from unittest.mock import patch
from django.test import TestCase
from . import test_application_workspace as fixtures
from .application_workspace import create_application
from .application_question_store import import_questions, analyze_questions, plan_application, planning_input, edit_question
from .application_answer_writer import prepare_request, generate_answer
from .models import Applications, ApplicationAnswers, ApplicationPlans, ResumeEvidence
from app.application_planning.models import AnalysisBatch, QuestionAnalysis, Ask, ApplicationPlan, QuestionAssignment, RequirementCoverage
from app.application_writing.models import WriterOutput, AnswerSentence, SupportRef, SemanticResult


class Planner:
    def analyze(self,questions,target):
        return AnalysisBatch(questions=[QuestionAnalysis(question_id=q.question_id,constraints=q.constraints,
            asks_for=[Ask(key='technical_contribution',source_quote='기술')]) for q in questions])
    def plan(self,data):
        exp=data.experiences[0]; eid=exp.evidence[0].evidence_id
        return ApplicationPlan(assignments=[QuestionAssignment(question_id=q.question_id,
            primary_experience_ids=[exp.experience_id],story_focus='직접 기술 기여',core_evidence_ids=[eid],rationale='확인 사실만 사용',
            requirement_coverage=[RequirementCoverage(requirement='technical_contribution',status='satisfied',evidence_ids=[eid],reason='본인 수행 확인')]) for q in data.questions])


class Client:
    def __init__(self,hook=None): self.calls=0; self.hook=hook
    def write(self,payload,*,rewrite=None):
        self.calls+=1
        if self.hook: self.hook()
        eid=payload['core'][0]['evidence_id']
        return WriterOutput(question_id=payload['question']['question_id'],sentences=[AnswerSentence(
            text='모델 학습을 직접 수행했습니다.',claim_types=['evidence'],support_refs=[SupportRef(source_type='evidence',source_id=eid)])])
    def verify(self,payload):
        self.calls+=1; w=payload['writer_input']
        return SemanticResult(question_id=w['question']['question_id'],factual_issues=[],quality_issues=[],
            expressed_core_evidence_ids=[f['evidence_id'] for f in w['core']],covered_requirements=['technical_contribution'],story_focus_preserved=True)


class ApplicationAnswerWriterTests(TestCase):
    def setUp(self):
        fixtures.ApplicationWorkspaceTests.setUp(self)
        self.app=create_application(user_id=self.user.pk,base_resume_id=self.base.pk,idempotency_key='phase4b')
        self.q=import_questions(user_id=self.user.pk,application_id=self.app.pk,questions=['기술 경험을 설명하세요.'])[0]
        self.planner=Planner()
        analyze_questions(user_id=self.user.pk,application_id=self.app.pk,client=self.planner)
        plan_application(user_id=self.user.pk,application_id=self.app.pk,client=self.planner)
    def generate(self,client=None):
        return generate_answer(user_id=self.user.pk,application_id=self.app.pk,question_id=self.q.pk,client=client or Client())
    def test_saves_generated_draft_without_new_evidence_or_plan_pollution(self):
        _,before=planning_input(user_id=self.user.pk,application_id=self.app.pk)
        count=ResumeEvidence.objects.count(); client=Client(); result=self.generate(client)
        self.assertEqual(result.status,'READY'); self.assertEqual(client.calls,2)
        row=ApplicationAnswers.objects.get(question=self.q)
        self.assertEqual((row.source_type,row.status,row.topic_resolved),('ai_generated','draft',False))
        self.assertEqual(row.content,result.final_text); self.assertEqual(ResumeEvidence.objects.count(),count)
        data,after=planning_input(user_id=self.user.pk,application_id=self.app.pk)
        self.assertEqual(before,after); self.assertEqual(data.answers,[])
    def test_existing_user_draft_not_overwritten(self):
        ApplicationAnswers.objects.create(question=self.q,answer_key='draft',content='개인 초안',source_type='user_draft',status='draft')
        plan_application(user_id=self.user.pk,application_id=self.app.pk,client=self.planner)
        self.generate()
        self.assertEqual(ApplicationAnswers.objects.get(question=self.q,answer_key='draft').content,'개인 초안')
        self.assertEqual(ApplicationAnswers.objects.filter(question=self.q).count(),2)
    def test_stale_question_blocked_before_writer(self):
        edit_question(user_id=self.user.pk,question_id=self.q.pk,raw_text='기술 변경')
        client=Client(); result=self.generate(client)
        self.assertEqual(result.status,'BLOCKED'); self.assertEqual(client.calls,0)
    def test_evidence_change_stales_plan(self):
        self.old.normalized_fact='사실 변경'; self.old.save()
        client=Client(); result=self.generate(client)
        self.assertEqual(result.status,'BLOCKED'); self.assertEqual(client.calls,0)
    def test_inactive_evidence_not_writer_input(self):
        self.old.assertion_state='superseded'; self.old.save()
        client=Client(); result=self.generate(client)
        self.assertEqual(result.status,'BLOCKED'); self.assertEqual(client.calls,0)
    def test_wrong_owner_never_calls_writer(self):
        client=Client()
        with self.assertRaises(Applications.DoesNotExist):
            generate_answer(user_id=self.other.pk,application_id=self.app.pk,question_id=self.q.pk,client=client)
        self.assertEqual(client.calls,0)
    def test_changed_during_generation_not_saved(self):
        def change(): self.old.normalized_fact='다른 내용'; self.old.save()
        with self.assertRaises(ValueError): self.generate(Client(hook=change))
        self.assertFalse(ApplicationAnswers.objects.filter(source_type='ai_generated').exists())
    def test_plan_contract_changed_during_generation_not_saved(self):
        def change():
            row=ApplicationPlans.objects.get(application=self.app)
            row.content['plan']['assignments'][0]['story_focus']='다른 초점'; row.save()
        with self.assertRaises(ValueError): self.generate(Client(hook=change))
        self.assertFalse(ApplicationAnswers.objects.filter(source_type='ai_generated').exists())
