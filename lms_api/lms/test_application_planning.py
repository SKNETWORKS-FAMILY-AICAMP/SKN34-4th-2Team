"""Fake structured model + isolated PostgreSQL. No real LLM calls."""
from copy import deepcopy
from unittest import skipUnless
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from django.test import TestCase, TransactionTestCase
from django.db import connection, connections
from django.db.migrations.executor import MigrationExecutor

from . import test_application_workspace as fixtures  # includes production settings guard
from .models import (ApplicationQuestions, ApplicationAnswers, ApplicationPlans, Applications,
                     ResumeEvidence, ResumeExperiences, ResumeExperienceBindings)
from .application_workspace import create_application
from .resume_experience_store import create_experience, record_user_evidence
from .application_question_store import (
    import_questions, edit_question, open_question, save_answer, open_answer,
    analyze_questions, planning_input, plan_application, reusable_plan,
)
from app.application_planning.models import (
    AnalysisBatch, QuestionAnalysis, Ask, Constraints, ApplicationPlan, QuestionAssignment, Gap, Fact,
)
from app.application_planning.engine import parse_constraints, validate_plan


class FakeClient:
    def __init__(self):
        self.analysis_calls = self.plan_calls = 0
        self.analysis_hook = self.plan_hook = None
    def analyze(self, questions, target):
        self.analysis_calls += 1
        rows = []
        for q in questions:
            keys = [('result', '결과')] if '결과' in q.raw_text else [('technical_contribution', '기술')]
            if '지원 이유' in q.raw_text: keys = [('company_motivation', '지원 이유'), ('preparation_effort', '준비 노력')]
            rows.append(QuestionAnalysis(question_id=q.question_id, constraints=q.constraints,
                asks_for=[Ask(key=k, source_quote=quote) for k,quote in keys]))
        result = AnalysisBatch(questions=rows)
        if self.analysis_hook: self.analysis_hook(result)
        return result
    def plan(self, data):
        self.plan_calls += 1
        self.last_input = data
        exp = data.experiences[0] if data.experiences else None
        core = [exp.evidence[0].evidence_id] if exp and exp.evidence else []
        result = ApplicationPlan(assignments=[QuestionAssignment(question_id=q.question_id,
            primary_experience_ids=[exp.experience_id] if exp else [], story_focus='직접 기술 기여',
            core_evidence_ids=core, rationale='문항과 실제 경험 연결') for q in data.questions])
        if self.plan_hook: self.plan_hook(result)
        return result


class ApplicationPlanningTests(TestCase):
    def setUp(self):
        fixtures.ApplicationWorkspaceTests.setUp(self)
        self.app = create_application(user_id=self.user.pk, base_resume_id=self.base.pk, idempotency_key='plan')
        self.questions = import_questions(user_id=self.user.pk, application_id=self.app.pk,
            questions=['지원 이유와 준비 노력 (1000자 이내, 공백 포함)', '직무 기술 경험', '도전 경험과 결과'])
        self.client = FakeClient()
    def analyze(self):
        return analyze_questions(user_id=self.user.pk, application_id=self.app.pk, client=self.client)
    def plan(self):
        return plan_application(user_id=self.user.pk, application_id=self.app.pk, client=self.client)
    def inputs(self):
        return planning_input(user_id=self.user.pk, application_id=self.app.pk)[0]

    def test_snapshot_import_retry_preserves_original(self):
        raw = [q.raw_text for q in self.questions]
        again = import_questions(user_id=self.user.pk, application_id=self.app.pk, questions=raw)
        self.assertEqual([q.pk for q in again], [q.pk for q in self.questions])
        raw[0] = '외부 원문 변경'
        self.questions[0].refresh_from_db()
        self.assertNotEqual(raw[0], self.questions[0].raw_text)

    def test_analysis_batch_complex_question_and_cache(self):
        result = self.analyze()
        self.assertEqual(len(result), 3)
        self.assertEqual(len(result[0].asks_for), 2)
        self.analyze()
        self.assertEqual(self.client.analysis_calls, 1)
        self.questions[0].refresh_from_db()
        self.assertEqual(self.questions[0].character_limit, 1000)

    def test_no_invented_limit(self):
        self.assertIsNone(parse_constraints('직무 기술 경험').character_limit)
        self.assertIsNone(parse_constraints('직무 기술 경험').include_spaces)
        self.assertEqual(parse_constraints('500바이트 공백 제외').count_unit, 'bytes')
        self.assertFalse(parse_constraints('500바이트 공백 제외').include_spaces)
        self.assertIsNone(parse_constraints('500자 또는 1000자').character_limit)

    def test_analyzer_cannot_invent_constraints_or_quotes(self):
        self.client.analysis_hook = lambda batch: setattr(batch.questions[1].constraints, 'character_limit', 1000)
        with self.assertRaises(ValueError): self.analyze()
        self.assertEqual(ApplicationQuestions.objects.exclude(analysis={}).count(), 0)
        self.client.analysis_hook = lambda batch: setattr(batch.questions[1].asks_for[0], 'source_quote', '없는 문구')
        with self.assertRaises(ValueError): self.analyze()

    def test_edit_invalidates_analysis_and_import_does_not_overwrite_edit(self):
        self.analyze(); self.plan()
        q = self.questions[1]
        edit_question(user_id=self.user.pk, question_id=q.pk, raw_text='새 기술 경험')
        q.refresh_from_db()
        self.assertEqual(q.analysis, {})
        self.assertIsNone(q.analysis_version)
        with self.assertRaises(ValueError): self.plan()
        again = import_questions(user_id=self.user.pk, application_id=self.app.pk,
            questions=[row.raw_text for row in self.questions])
        self.assertEqual(again[1].raw_text, '새 기술 경험')

    def test_cross_user_question_answer_access(self):
        q = self.questions[0]
        with self.assertRaises(ApplicationQuestions.DoesNotExist): open_question(user_id=self.other.pk, question_id=q.pk)
        with self.assertRaises(ApplicationQuestions.DoesNotExist): save_answer(user_id=self.other.pk, question_id=q.pk, content='bad')
        a = save_answer(user_id=self.user.pk, question_id=q.pk, content='사용자 초안')
        with self.assertRaises(ApplicationAnswers.DoesNotExist): open_answer(user_id=self.other.pk, answer_id=a.pk)

    def test_answers_are_documents_not_evidence(self):
        before = ResumeEvidence.objects.count()
        a = save_answer(user_id=self.user.pk, question_id=self.questions[0].pk, content='Python 전문가입니다')
        b = save_answer(user_id=self.user.pk, question_id=self.questions[0].pk, content='초안 수정')
        self.assertEqual(a.pk, b.pk)
        self.assertEqual(ResumeEvidence.objects.count(), before)
        with self.assertRaises(ValueError): save_answer(user_id=self.user.pk, question_id=self.questions[0].pk, content='AI', source_type='ai_generated')

    def test_all_questions_planned_at_once_and_cached(self):
        self.analyze(); result = self.plan(); self.plan()
        self.assertEqual(len(result.plan.assignments), 3)
        self.assertEqual(self.client.plan_calls, 1)
        self.assertEqual(len(result.duplicate_story_warnings[0]), 3)
        self.assertEqual(result.next_question.category, 'applicant_intent')

    def test_same_experience_different_focus_allowed(self):
        self.analyze()
        self.client.plan_hook = lambda p: [setattr(a, 'story_focus', f'다른 초점 {i}') for i,a in enumerate(p.assignments)]
        self.assertEqual(self.plan().duplicate_story_warnings, [])

    def test_missing_result_gap_targets_experience(self):
        self.analyze(); result = self.plan()
        gap = result.plan.assignments[2].missing_information[0]
        self.assertEqual(gap.key, 'result')
        self.assertEqual(gap.target_experience_id, str(self.binding.experience_id))
        self.assertEqual(result.plan.assignments[2].result_evidence_ids, [])

    def test_foreign_experience_blocked(self):
        self.analyze()
        other = create_experience(user_id=self.other.pk, kind='project', title='Other')
        self.client.plan_hook = lambda p: setattr(p.assignments[0], 'primary_experience_ids', [str(other.pk)])
        with self.assertRaises(ValueError): self.plan()

    def test_evidence_from_other_experience_blocked(self):
        self.analyze()
        exp = create_experience(user_id=self.user.pk, kind='project', title='Unbound')
        ev = record_user_evidence(user_id=self.user.pk, experience_id=exp.pk, fact_type='action',
            normalized_fact='다른 경험 작업', evidence_quote='작업', answer_source_id='other', answer_text='작업')
        self.client.plan_hook = lambda p: setattr(p.assignments[0], 'core_evidence_ids', [str(ev.pk)])
        with self.assertRaises(ValueError): self.plan()

    def test_inactive_evidence_blocked_no_resurrection(self):
        self.analyze()
        for state in ('superseded', 'uncertain', 'contradicted', 'retracted'):
            self.old.assertion_state=state; self.old.save()
            self.client.plan_hook = lambda p: setattr(p.assignments[0], 'core_evidence_ids', [str(self.old.pk)])
            with self.assertRaises(ValueError): self.plan()
        self.assertEqual(ResumeEvidence.objects.count(), 1)
        self.assertNotIn('current_text', self.inputs().model_dump_json())

    def test_uncertain_conflict_removes_active_target_from_input(self):
        self.analyze()
        record_user_evidence(user_id=self.user.pk, experience_id=self.binding.experience_id, fact_type='action',
            normalized_fact='아마 팀원 작업', evidence_quote='팀원', answer_source_id='uncertain',
            answer_text='팀원', uncertain_conflict_id=self.old.pk)
        self.assertEqual(self.inputs().experiences[0].evidence, [])

    def test_result_cannot_use_action_as_result(self):
        self.analyze()
        self.client.plan_hook=lambda p: setattr(p.assignments[0], 'result_evidence_ids', [str(self.old.pk)])
        with self.assertRaises(ValueError): self.plan()

    def test_plan_stale_after_correction(self):
        self.analyze(); self.plan()
        self.assertIsNotNone(reusable_plan(user_id=self.user.pk, application_id=self.app.pk))
        record_user_evidence(user_id=self.user.pk, experience_id=self.binding.experience_id, fact_type='action',
            normalized_fact='API 연동', evidence_quote='API', answer_source_id='correct', answer_text='API', supersedes_evidence_id=self.old.pk)
        self.assertIsNone(reusable_plan(user_id=self.user.pk, application_id=self.app.pk))
        self.plan(); self.assertEqual(self.client.plan_calls, 2)

    def test_target_changes_analysis_and_plan_stale(self):
        self.analyze(); self.plan()
        self.app.target_snapshot={'description':'새 대상'}; self.app.save()
        with self.assertRaises(ValueError): self.plan()

    def test_inputs_changed_during_analysis_or_planning_block_save(self):
        def mutate(_): edit_question(user_id=self.user.pk, question_id=self.questions[1].pk, raw_text='변경 기술 경험')
        self.client.analysis_hook=mutate
        with self.assertRaises(ValueError): self.analyze()
        self.client.analysis_hook=None; self.analyze()
        self.client.plan_hook=mutate
        # Use a new text, rather than a no-op update.
        self.client.plan_hook=lambda _: edit_question(user_id=self.user.pk, question_id=self.questions[1].pk, raw_text='두 번째 기술 변경')
        with self.assertRaises(ValueError): self.plan()
        self.assertEqual(ApplicationPlans.objects.count(),0)

    def test_dedupe_confirmed_intent_and_existing_evidence(self):
        self.analyze()
        save_answer(user_id=self.user.pk, question_id=self.questions[0].pk, content='지원 관심',
                    status='confirmed', confirmation_key='company_motivation', topic_resolved=True)
        result=self.plan()
        self.assertEqual(result.next_question.key,'result')
        self.assertEqual(result.next_question.target_experience_id,str(self.binding.experience_id))
        save_answer(user_id=self.user.pk, question_id=self.questions[2].pk, content='모르겠습니다',
            answer_key='result-confirmation', source_type='user_supplement', status='confirmed',
            target_experience_id=self.binding.experience_id, confirmation_key='result')
        self.assertIsNone(self.plan().next_question)

    def test_gap_wrong_experience_blocked(self):
        self.analyze()
        self.client.plan_hook=lambda p: p.assignments[0].missing_information.append(Gap(key='result',
            category='applicant_evidence', target_experience_id='other',reason='missing',importance='high'))
        with self.assertRaises(ValueError): self.plan()

    def test_company_requirement_is_not_evidence(self):
        self.app.target_snapshot={'description':'Redis 필요'};self.app.save()
        self.analyze()
        self.client.plan_hook=lambda p: setattr(p.assignments[0],'core_evidence_ids',['Redis'])
        with self.assertRaises(ValueError): self.plan()

    def test_no_experience_requirement_does_not_invent_gap_target(self):
        ResumeExperienceBindings.objects.all().delete()
        self.analyze()
        # New contract requires a real selected Experience for experience gaps.
        # An unbound workspace stays blocked rather than inventing an identity.
        with self.assertRaisesRegex(ValueError, 'explicit Experience scope'):
            self.plan()

    def test_source_snapshot_is_detached_from_external_mutation(self):
        external=['직무 기술 질문']
        q=import_questions(user_id=self.user.pk,application_id=self.app.pk,questions=external,
            source_type='recruit_role',source_reference='role-v1')[0]
        external[0]='외부 개정'
        q.refresh_from_db();self.assertEqual(q.raw_text,'직무 기술 질문')

    def test_question_delete_cascades_answers(self):
        q=self.questions[0]
        a=save_answer(user_id=self.user.pk,question_id=q.pk,content='draft')
        q.delete();self.assertFalse(ApplicationAnswers.objects.filter(pk=a.pk).exists())

    def test_duplicate_missing_question_id_blocked(self):
        self.analyze()
        self.client.plan_hook=lambda p: setattr(p.assignments[1],'question_id',p.assignments[0].question_id)
        with self.assertRaises(ValueError): self.plan()

    def test_overlapping_evidence_tiers_blocked(self):
        self.analyze()
        self.client.plan_hook=lambda p: setattr(p.assignments[0],'supporting_evidence_ids',p.assignments[0].core_evidence_ids[:])
        with self.assertRaises(ValueError): self.plan()

    def test_invented_gap_target_blocked_for_intent(self):
        self.analyze()
        self.client.plan_hook=lambda p:p.assignments[0].missing_information.append(Gap(key='company_motivation',
            category='applicant_intent',target_experience_id=str(self.binding.experience_id),reason='intent',importance='high'))
        with self.assertRaises(ValueError): self.plan()

    def test_wrong_answer_target_and_empty_intent(self):
        other=create_experience(user_id=self.other.pk,kind='project',title='foreign')
        with self.assertRaises(ValueError):
            save_answer(user_id=self.user.pk,question_id=self.questions[0].pk,content='x',target_experience_id=other.pk)
        self.analyze()
        save_answer(user_id=self.user.pk,question_id=self.questions[0].pk,content='',status='confirmed',confirmation_key='company_motivation')
        self.assertEqual(self.plan().next_question.key,'company_motivation')

    def test_confirmed_result_is_selected_not_invented(self):
        ev=record_user_evidence(user_id=self.user.pk,experience_id=self.binding.experience_id,fact_type='result',
            normalized_fact='수동 작업 시간 감소 확인',evidence_quote='시간 감소',answer_source_id='result',answer_text='시간 감소')
        self.analyze()
        def select(plan):
            row=plan.assignments[2]
            row.core_evidence_ids=[str(self.old.pk)]
            row.supporting_evidence_ids=[str(ev.pk)]
            row.result_evidence_ids=[str(ev.pk)]
        self.client.plan_hook=select
        self.assertEqual(self.plan().plan.assignments[2].result_evidence_ids,[str(ev.pk)])

    def test_ignored_available_required_result_blocked(self):
        record_user_evidence(user_id=self.user.pk,experience_id=self.binding.experience_id,fact_type='result',
            normalized_fact='결과 확인',evidence_quote='결과',answer_source_id='r2',answer_text='결과')
        self.analyze()
        with self.assertRaises(ValueError): self.plan()

    def test_result_selection_need_not_duplicate_supporting_tier(self):
        ev=record_user_evidence(user_id=self.user.pk,experience_id=self.binding.experience_id,fact_type='result',
            normalized_fact='오류 해결',evidence_quote='오류 해결',answer_source_id='separate-result',answer_text='오류 해결')
        self.analyze()
        self.client.plan_hook=lambda p:setattr(p.assignments[2],'result_evidence_ids',[str(ev.pk)])
        result=self.plan().plan.assignments[2]
        self.assertEqual(result.result_evidence_ids,[str(ev.pk)])
        self.assertNotIn(str(ev.pk),result.supporting_evidence_ids)

    def test_unknown_intent_answer_dedupes_but_remains_a_gap(self):
        self.analyze()
        save_answer(user_id=self.user.pk,question_id=self.questions[0].pk,content='잘 모르겠습니다',
            status='confirmed',confirmation_key='company_motivation')
        result=self.plan()
        self.assertTrue(any(g.key=='company_motivation' for g in result.plan.assignments[0].missing_information))
        self.assertEqual(result.next_question.key,'result')

    def test_application_delete_cascades_questions_answers_plans_not_evidence(self):
        self.analyze();self.plan()
        save_answer(user_id=self.user.pk,question_id=self.questions[0].pk,content='draft')
        self.app.delete()
        self.assertEqual(ApplicationQuestions.objects.count(),0)
        self.assertEqual(ApplicationAnswers.objects.count(),0)
        self.assertEqual(ApplicationPlans.objects.count(),0)
        self.assertEqual(ResumeEvidence.objects.count(),1)


@skipUnless(connection.vendor=='postgresql','requires PostgreSQL')
class ApplicationPlanningPostgresTests(TransactionTestCase):
    setUp=ApplicationPlanningTests.setUp
    def test_concurrent_question_import(self):
        barrier=Barrier(2)
        args=dict(user_id=self.user.pk,application_id=self.app.pk,questions=['기술 질문'],source_reference='parallel')
        def run():
            connections.close_all()
            try:
                barrier.wait(timeout=10)
                return import_questions(**args)[0].pk
            finally: connections.close_all()
        with ThreadPoolExecutor(max_workers=2) as pool:
            fs=[pool.submit(run) for _ in range(2)];ids=[f.result(timeout=20) for f in fs]
        self.assertEqual(ids[0],ids[1])
        self.assertEqual(ApplicationQuestions.objects.filter(source_reference='parallel').count(),1)

    def test_migration_rollback_reapply_preserves_old_core(self):
        def snapshot():
            rows=[]
            with connection.cursor() as cur:
                for table in ('applications','resumes','resume_experiences','resume_evidence','resume_experience_bindings'):
                    cur.execute(f'SELECT to_jsonb(t) FROM {table} t ORDER BY 1')
                    rows.append(cur.fetchall())
            return rows
        before=snapshot()
        try:
            MigrationExecutor(connection).migrate([('lms','0012_application_workspace')])
            self.assertEqual(before,snapshot())
            MigrationExecutor(connection).migrate([('lms','0013_application_questions_answers')])
            self.assertEqual(before,snapshot())
            import_questions(user_id=self.user.pk,application_id=self.app.pk,questions=['기술 질문'])
            with connection.cursor() as cur:
                cur.execute("SELECT to_regclass('application_questions'),to_regclass('application_answers'),to_regclass('application_plans')")
                self.assertEqual(cur.fetchone(),('application_questions','application_answers','application_plans'))
        finally:
            executor=MigrationExecutor(connection);executor.migrate(executor.loader.graph.leaf_nodes())
