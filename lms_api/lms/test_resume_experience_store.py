"""Persistence invariants on a disposable test DB; no RDS or LLM calls."""

from copy import deepcopy
from unittest.mock import patch

from django.test import TestCase

from .models import Cohorts, ResumeEvidence, ResumeExperienceBindings, ResumeExperiences, Resumes, Users
from .resume_experience_store import (
    ITEM_KEY_FIELD, bind_resume_item, build_v2_review_input, clone_bindings_for_tailored_resume,
    create_experience, ensure_resume_item_binding, load_active_evidence,
    record_resume_evidence, record_user_evidence,
)


class ResumeExperienceStoreTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.cohort = Cohorts.objects.create(code='v2-test', name='V2', status='active', is_active=True)
        cls.user = Users.objects.create(email='v2@example.test', password='unused', display_name='V2',
                                        role='student', cohort=cls.cohort, is_active=True, must_change_password=False)
        cls.other = Users.objects.create(email='other@example.test', password='unused', display_name='Other',
                                         role='student', cohort=cls.cohort, is_active=True, must_change_password=False)
        cls.resume = Resumes.objects.create(
            cohort=cls.cohort, user=cls.user, title='Base', is_base_resume=True,
            content={'projects': [
                {'name': 'Project A', 'description': '모델 학습을 직접 수행했습니다.'},
                {'name': 'Project B', 'description': '모델 학습을 직접 수행했습니다.'},
            ]},
        )

    def _evidence(self, experience, quote='모델 학습'):
        return record_resume_evidence(
            user_id=self.user.pk, experience_id=experience.pk, fact_type='action',
            normalized_fact='모델 학습을 직접 수행', evidence_quote=quote,
            source_id='resume-source', source_text='모델 학습을 직접 수행했습니다.',
        )

    def _answer(self, experience, source='answer-1', **extra):
        return record_user_evidence(
            user_id=self.user.pk, experience_id=experience.pk, fact_type='action',
            normalized_fact='API 연동 담당', evidence_quote='API 연동',
            answer_source_id=source, answer_text='저는 API 연동을 담당했습니다.', **extra,
        )

    def test_correction_is_strictly_experience_local(self):
        a = create_experience(user_id=self.user.pk, kind='project', title='A')
        b = create_experience(user_id=self.user.pk, kind='project', title='B')
        old_a, old_b = self._evidence(a), self._evidence(b)
        new = self._answer(a, supersedes_evidence_id=old_a.pk)
        old_a.refresh_from_db()
        old_b.refresh_from_db()
        self.assertEqual(old_a.assertion_state, 'superseded')
        self.assertEqual(old_b.assertion_state, 'resume_stated')
        self.assertEqual(new.supersedes_evidence_id, old_a.pk)
        self.assertEqual([row.pk for row in load_active_evidence(user_id=self.user.pk, experience_id=b.pk)], [old_b.pk])
        with self.assertRaises(ValueError):
            self._answer(a, supersedes_evidence_id=old_b.pk)

    def test_repeated_supersession_is_rejected(self):
        exp = create_experience(user_id=self.user.pk, kind='project', title='A')
        old = self._evidence(exp)
        self._answer(exp, supersedes_evidence_id=old.pk)
        with self.assertRaises(ValueError):
            self._answer(exp, source='answer-2', supersedes_evidence_id=old.pk)
        self.assertEqual(ResumeEvidence.objects.filter(experience=exp).count(), 2)

    def test_correction_rolls_back_new_evidence_if_target_update_fails(self):
        exp = create_experience(user_id=self.user.pk, kind='project', title='A')
        old = self._evidence(exp)
        original_save = ResumeEvidence.save

        def fail_target_save(instance, *args, **kwargs):
            if instance.pk == old.pk:
                raise RuntimeError('simulated DB update failure')
            return original_save(instance, *args, **kwargs)

        with patch.object(ResumeEvidence, 'save', fail_target_save):
            with self.assertRaises(RuntimeError):
                self._answer(exp, supersedes_evidence_id=old.pk)
        old.refresh_from_db()
        self.assertEqual(old.assertion_state, 'resume_stated')
        self.assertEqual(ResumeEvidence.objects.filter(experience=exp).count(), 1)

    def test_uncertain_blocks_writer_without_superseding(self):
        exp = create_experience(user_id=self.user.pk, kind='project', title='A')
        old = self._evidence(exp)
        uncertain = self._answer(exp, uncertain_conflict_id=old.pk)
        old.refresh_from_db()
        self.assertEqual(old.assertion_state, 'resume_stated')
        self.assertEqual(uncertain.assertion_state, 'uncertain')
        self.assertEqual(load_active_evidence(user_id=self.user.pk, experience_id=exp.pk), [])

    def test_active_state_filter(self):
        exp = create_experience(user_id=self.user.pk, kind='project', title='A')
        for state in ('resume_stated', 'user_asserted', 'uncertain', 'contradicted', 'retracted', 'superseded'):
            ResumeEvidence.objects.create(experience=exp, fact_type='action', normalized_fact=state,
                                          evidence_quote=state, source_type='user_answer', source_id='x',
                                          assertion_state=state)
        self.assertEqual({row.assertion_state for row in load_active_evidence(
            user_id=self.user.pk, experience_id=exp.pk)}, {'resume_stated', 'user_asserted'})

    def test_lazy_binding_survives_reorder(self):
        binding = ensure_resume_item_binding(user_id=self.user.pk, resume_id=self.resume.pk,
                                             section='projects', index=0)
        first_experience_id = binding.experience_id
        self.resume.refresh_from_db()
        content = deepcopy(self.resume.content)
        content['projects'].reverse()
        self.resume.content = content
        self.resume.save(update_fields=['content'])
        rebound = ensure_resume_item_binding(user_id=self.user.pk, resume_id=self.resume.pk,
                                             section='projects', index=1)
        self.assertEqual(rebound.experience_id, first_experience_id)
        self.assertEqual(rebound.field_path, 'projects[1].description')
        self.assertEqual(ResumeExperiences.objects.count(), 1)

    def test_existing_react_item_id_is_used_without_json_change(self):
        resume = Resumes.objects.create(
            cohort=self.cohort, user=self.user, title='Native ids',
            content={'projects': [{'id': 'prj-123', 'name': 'Existing', 'description': 'API 구축'}]},
        )
        before = deepcopy(resume.content)
        binding = ensure_resume_item_binding(user_id=self.user.pk, resume_id=resume.pk,
                                             section='projects', index=0)
        resume.refresh_from_db()
        self.assertEqual(binding.item_key, 'projects:prj-123')
        self.assertEqual(resume.content, before)

    def test_tailored_copy_shares_experience_and_evidence(self):
        binding = ensure_resume_item_binding(user_id=self.user.pk, resume_id=self.resume.pk,
                                             section='projects', index=0)
        self._evidence(binding.experience)
        self.resume.refresh_from_db()
        tailored = Resumes.objects.create(cohort=self.cohort, user=self.user, title='Tailored',
                                          base_resume=self.resume, content=deepcopy(self.resume.content))
        before = (ResumeExperiences.objects.count(), ResumeEvidence.objects.count())
        cloned = clone_bindings_for_tailored_resume(user_id=self.user.pk,
                                                     source_resume_id=self.resume.pk,
                                                     tailored_resume_id=tailored.pk)
        self.assertEqual(len(cloned), 1)
        self.assertEqual(cloned[0].experience_id, binding.experience_id)
        self.assertEqual((ResumeExperiences.objects.count(), ResumeEvidence.objects.count()), before)

    def test_ownership_and_no_title_guessing(self):
        own = create_experience(user_id=self.user.pk, kind='project', title='Same title')
        foreign = create_experience(user_id=self.other.pk, kind='project', title='Same title')
        key = 'item-1'
        with self.assertRaises(PermissionError):
            bind_resume_item(user_id=self.user.pk, resume_id=self.resume.pk, experience_id=foreign.pk,
                             item_key=key, field_path='projects[0].description', display_order=0)
        with self.assertRaises(PermissionError):
            load_active_evidence(user_id=self.other.pk, experience_id=own.pk)
        self.assertEqual(ResumeExperienceBindings.objects.count(), 0)

    def test_adapter_loads_only_owned_active_evidence(self):
        binding = ensure_resume_item_binding(user_id=self.user.pk, resume_id=self.resume.pk,
                                             section='projects', index=0)
        active = self._evidence(binding.experience)
        ResumeEvidence.objects.create(experience=binding.experience, fact_type='action',
                                      normalized_fact='old', evidence_quote='old', source_type='resume_text',
                                      source_id='x', assertion_state='superseded')
        request = build_v2_review_input(user_id=self.user.pk, resume_id=self.resume.pk,
                                        item_key=binding.item_key)
        self.assertEqual(request.experience.experience_id, str(binding.experience_id))
        self.assertEqual([e.evidence_id for e in request.experience.existing_evidence], [str(active.pk)])
        with self.assertRaises(PermissionError):
            build_v2_review_input(user_id=self.other.pk, resume_id=self.resume.pk,
                                  item_key=binding.item_key)

    def test_adapter_input_runs_in_offline_engine(self):
        binding = ensure_resume_item_binding(user_id=self.user.pk, resume_id=self.resume.pk,
                                             section='projects', index=0)
        evidence = self._evidence(binding.experience)
        request = build_v2_review_input(user_id=self.user.pk, resume_id=self.resume.pk,
                                        item_key=binding.item_key)
        from app.resume_review_v2.engine import ReviewEngineV2
        from app.resume_review_v2.models import AnalystOutput, RevisionPlan, Usage

        class OfflineLLM:
            def analyze(self, incoming):
                assert [e.evidence_id for e in incoming.experience.existing_evidence] == [str(evidence.pk)]
                return AnalystOutput(
                    experience_id=incoming.experience.experience_id, extracted_evidence=[],
                    plan=RevisionPlan(objective='No edit', operation='no_change'),
                ), Usage(calls=1)

        result = ReviewEngineV2(OfflineLLM()).run(request)
        self.assertEqual(result.validation.status, 'READY')
        self.assertEqual(result.usage.calls, 1)
