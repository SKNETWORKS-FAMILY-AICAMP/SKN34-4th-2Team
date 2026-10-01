"""Existing schema, isolated local DB, no LLM or crawler calls."""
from copy import deepcopy
from unittest.mock import patch
from django.test import TestCase
from . import test_recruit_role_context as role_fixtures
from .test_application_answer_writer import Planner
from .models import JobRequirementProfiles, ResumeEvidence, ApplicationAnswers
from .recruit_role_store import create_role_application, validate_content
from .application_question_store import _target,import_questions,analyze_questions,plan_application,planning_input
from .application_answer_writer import prepare_request,generate_answer
from .application_workspace import create_application
from app.job_requirements import requirement_cache_key
from app.application_writing.models import WriterOutput,AnswerSentence,SupportRef,SemanticResult
from app.application_writing.engine import writer_input,check_sources


class ProfileWiringTests(TestCase):
    def setUp(self):
        role_fixtures.RecruitRoleTests.setUp(self)
        self.role=role_fixtures.RecruitRoleTests.role(self)
        self.rows=[dict(id='req-1',group='preferred',label='Python 개발 경험',posting_quote='Python 개발 경험 우대',kind='skill',kind_basis=''),
                   dict(id='req-2',group='must',label='학사 이상',posting_quote='학사 이상',kind='eligibility',kind_basis='학력 조건')]
        self.key=requirement_cache_key(dict(job_id='J1',snapshot_hash='S1'))
        self.profile=JobRequirementProfiles.objects.create(key=self.key,requirements=deepcopy(self.rows))
        self.old.normalized_fact='Python으로 데이터 분석 모델을 구현'; self.old.save()
    def app(self,key='wire',**extra):
        values=dict(user_id=self.user.pk,role_id=self.role.pk,base_resume_id=self.base.pk,idempotency_key=key,
                    job_id='J1',target_snapshot={'snapshot_hash':'S1'})
        values.update(extra)
        return create_role_application(**values)
    def planned(self):
        app=self.app(); q=import_questions(user_id=self.user.pk,application_id=app.pk,questions=['Python 기술 기여를 설명하세요.'])[0]
        analyze_questions(user_id=self.user.pk,application_id=app.pk,client=Planner())
        plan_application(user_id=self.user.pk,application_id=app.pk,client=Planner())
        return app,q
    def test_array_input_validates_no_import_error_and_no_information_loss(self):
        parsed,_=validate_content('source',deepcopy(self.rows),[])
        self.assertEqual(parsed,self.rows)
        role=role_fixtures.RecruitRoleTests.role(self,requirements=deepcopy(self.rows))
        role.refresh_from_db(); self.assertEqual(role.requirements,self.rows)
    def test_auto_link_reuses_existing_profile_without_llm_or_new_profile(self):
        with patch('langchain_openai.ChatOpenAI',side_effect=AssertionError('LLM forbidden')) as llm:
            app=self.app(); retry=self.app(); llm.assert_not_called()
        self.assertEqual(app.pk,retry.pk); self.assertEqual(app.requirement_profile_id,self.profile.pk)
        self.assertEqual(JobRequirementProfiles.objects.count(),1)
    def test_missing_profile_keeps_null_and_does_not_extract(self):
        self.profile.delete()
        with patch('langchain_openai.ChatOpenAI',side_effect=AssertionError('LLM forbidden')) as llm:
            app=self.app(); llm.assert_not_called()
        self.assertIsNone(app.requirement_profile_id); self.assertEqual(JobRequirementProfiles.objects.count(),0)
    def test_job_snapshot_is_not_role_content_hash(self):
        app=self.app()
        self.assertEqual(app.target_snapshot['snapshot_hash'],'S1')
        self.assertEqual(app.target_snapshot['role_version'],self.role.content_hash)
        self.assertNotEqual('S1',self.role.content_hash)
        self.assertEqual(app.requirement_profile_id,self.key)
    def test_role_job_reference_used_when_posting_snapshot_available(self):
        self.role.job_id='J1'; self.role.save(update_fields=['job_id'])
        app=create_role_application(user_id=self.user.pk,role_id=self.role.pk,base_resume_id=self.base.pk,
            idempotency_key='infer',target_snapshot={'snapshot_hash':'S1'})
        self.assertEqual(app.job_id,'J1'); self.assertEqual(app.requirement_profile_id,self.key)
    def test_linked_role_without_posting_snapshot_does_not_guess(self):
        self.role.job_id='J1'; self.role.save(update_fields=['job_id'])
        app=create_role_application(user_id=self.user.pk,role_id=self.role.pk,base_resume_id=self.base.pk,idempotency_key='role-only')
        self.assertIsNone(app.requirement_profile_id); self.assertNotIn('snapshot_hash',app.target_snapshot)
    def test_conflicting_role_job_cannot_link_a_different_profile(self):
        self.role.job_id='J2'; self.role.save(update_fields=['job_id'])
        with self.assertRaises(ValueError): self.app()
    def test_stale_snapshot_does_not_link_profile_of_another_snapshot(self):
        app=self.app(target_snapshot={'snapshot_hash':'S2'})
        self.assertIsNone(app.requirement_profile_id)
    def test_wrong_explicit_profile_rejected(self):
        with self.assertRaises(ValueError): self.app(target_snapshot={'snapshot_hash':'S2'},requirement_profile_key=self.key)
    def test_role_only_does_not_use_role_hash_as_job_hash(self):
        app=self.app(job_id=None,target_snapshot={})
        self.assertIsNone(app.requirement_profile_id); self.assertNotIn('snapshot_hash',app.target_snapshot)
    def test_structured_and_role_context_parallel_and_lossless(self):
        app=self.app(); context=_target(app)
        self.assertEqual(context['requirements'],self.rows)
        self.assertEqual(context['recruit_role']['requirements'],self.role.requirements)
        self.assertEqual(context['requirement_profile_source']['snapshot_hash'],'S1')
        self.assertEqual(app.target_snapshot['recruit_role_snapshot']['requirements'],self.role.requirements)
    def test_profile_appearing_later_does_not_change_retry_identity_or_frozen_workspace(self):
        self.profile.delete(); app=self.app()
        JobRequirementProfiles.objects.create(key=self.key,requirements=deepcopy(self.rows))
        again=self.app(); self.assertEqual(app.pk,again.pk); self.assertIsNone(again.requirement_profile_id)
    def test_writer_boundary_auto_adapts_and_preserves_requirement_source(self):
        app,q=self.planned(); before=ResumeEvidence.objects.count()
        request=prepare_request(user_id=self.user.pk,application_id=app.pk)
        self.assertEqual([m.material_id for m in request.materials],['req-1'])
        self.assertEqual(request.materials[0].requirement_source.requirement.model_dump(),self.rows[0])
        check_sources(request)
        self.assertEqual(writer_input(request,str(q.pk))['context'][0]['source_type'],'target_context')
        self.assertEqual(ResumeEvidence.objects.count(),before)
    def test_profile_content_change_invalidates_cached_plan(self):
        app,q=self.planned()
        self.profile.requirements[0]['posting_quote']='Python 경력 필수'; self.profile.save()
        with self.assertRaises(ValueError): prepare_request(user_id=self.user.pk,application_id=app.pk)
    def test_requirement_order_changes_plan_hash_but_logical_refs_resolve(self):
        app,q=self.planned(); first=prepare_request(user_id=self.user.pk,application_id=app.pk)
        self.profile.requirements.reverse(); self.profile.save()
        # Existing hash guards conservatively stale analysis on JSON changes.
        # Logical source resolution itself must remain independent of array order.
        first.planning_input.target_context=_target(app); check_sources(first)
        analyze_questions(user_id=self.user.pk,application_id=app.pk,client=Planner())
        plan_application(user_id=self.user.pk,application_id=app.pk,client=Planner())
        second=prepare_request(user_id=self.user.pk,application_id=app.pk)
        self.assertEqual(first.materials[0].source_path,second.materials[0].source_path)
        self.assertEqual(first.materials[0].requirement_source.requirement_hash,second.materials[0].requirement_source.requirement_hash)
    def test_end_to_end_mock_target_reference_and_draft_storage(self):
        app,q=self.planned()
        class Writer:
            def write(self,payload,*,rewrite=None):
                eid=payload['core'][0]['evidence_id']
                return WriterOutput(question_id=str(q.pk),sentences=[AnswerSentence(text='귀사는 Python 개발 경험을 우대합니다.',
                    support_refs=[SupportRef(source_type='target_context',source_id='req-1')],claim_types=['target_context']),
                    AnswerSentence(text='Python으로 데이터 분석 모델을 구현했습니다.',support_refs=[SupportRef(source_type='evidence',source_id=eid)],claim_types=['evidence'])])
            def verify(self,payload):
                return SemanticResult(question_id=str(q.pk),factual_issues=[],quality_issues=[],
                    expressed_core_evidence_ids=[e['evidence_id'] for e in payload['writer_input']['core']],
                    covered_requirements=['technical_contribution'],story_focus_preserved=True)
        result=generate_answer(user_id=self.user.pk,application_id=app.pk,question_id=q.pk,client=Writer())
        self.assertEqual(result.status,'READY')
        self.assertEqual(result.candidate.sentences[0].support_refs[0].source_id,'req-1')
        self.assertEqual(ApplicationAnswers.objects.get(question=q,source_type='ai_generated').content,result.final_text)
