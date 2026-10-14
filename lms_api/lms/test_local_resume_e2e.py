import json
from unittest.mock import patch
from django.test import TestCase, override_settings
from django.core.exceptions import ImproperlyConfigured
from .local_resume_e2e_fixture import seed, EMAIL, PASSWORD
from .models import Users, Applications, ResumeExperiences, ResumeEvidence, Resumes, RecruitRoles
from .jwt_auth import issue_tokens, load_lms_user
from local_resume_e2e_settings import require_loopback

ROOT = '/api/local/resume-e2e'


class LocalE2ETests(TestCase):
    def setUp(self):
        self.user, self.base, self.role = seed()
        result = self.client.post(ROOT + '/login', json.dumps({'email': EMAIL, 'password': PASSWORD}), content_type='application/json').json()
        self.client.defaults['HTTP_AUTHORIZATION'] = 'Bearer ' + result['access']

    def post(self, path, body=None, status=200):
        response = self.client.post(ROOT + path, json.dumps(body or {}), content_type='application/json')
        self.assertEqual(response.status_code, status, response.content.decode())
        return response.json()

    def app(self, source='job_first'):
        return self.post('/applications/open-or-create', {'role_id': str(self.role.pk), 'base_resume_id': self.base.pk,
            'idempotency_key': 'same-http-operation', 'entry_source': source, 'user_id': 99999})

    def test_complete_mock_http_flow_reuse_sharing_and_reopen(self):
        first = self.app()
        self.assertEqual(first['id'], self.app('resume_first')['id'])
        prefix = '/applications/' + first['id']
        before = (ResumeExperiences.objects.count(), ResumeEvidence.objects.count())
        tailored = self.post(prefix + '/tailored-resume')
        self.assertEqual(tailored['tailored_resume_id'], self.post(prefix + '/tailored-resume')['tailored_resume_id'])
        self.assertEqual(before, (ResumeExperiences.objects.count(), ResumeEvidence.objects.count()))
        grouped = {rid: {b['experience_id'] for b in tailored['bindings'] if b['resume_id'] == rid}
                   for rid in (self.base.pk, tailored['tailored_resume_id'])}
        self.assertEqual(len(grouped[self.base.pk]), 3)
        self.assertEqual(grouped[self.base.pk], grouped[tailored['tailored_resume_id']])
        self.post(prefix + '/questions')
        self.assertEqual(len(self.post(prefix + '/questions')['questions']), 3)
        self.post(prefix + '/analyze')
        with patch('langchain_openai.ChatOpenAI', side_effect=AssertionError('external')) as paid:
            plan = self.post(prefix + '/plan')
            paid.assert_not_called()
        self.assertEqual(len(plan['planner']['plan']['assignments']), 3)
        self.assertIn('Phase 4A.7 GO', plan['semantic_status'])
        q1 = plan['planner']['plan']['assignments'][0]
        self.assertFalse(any(g['key'] == 'preparation_effort' for g in q1['missing_information']))
        self.assertTrue(any(g['key'] == 'company_motivation' for g in q1['missing_information']))
        facts = [f for e in plan['experiences'] for f in e['evidence']]
        self.assertFalse(any(f['normalized_fact'] == '모델 학습을 직접 구현' for f in facts))
        inactive = {str(f.pk) for f in ResumeEvidence.objects.exclude(assertion_state__in=['resume_stated', 'user_asserted'])}
        self.assertFalse(any(eid in inactive for a in plan['planner']['plan']['assignments']
            for key in ['core_evidence_ids','supporting_evidence_ids','result_evidence_ids'] for eid in a[key]))
        reopened = self.client.get(ROOT + prefix).json()
        self.assertEqual(plan['tailored_resume_id'], reopened['tailored_resume_id'])
        self.assertEqual(plan['counts'], reopened['counts'])
        self.assertEqual(Applications.objects.get(pk=first['id']).user_id, self.user.pk)

    def test_fixture_writer_uses_recorded_contract_and_validators(self):
        first=self.app(); prefix='/applications/'+first['id']
        for suffix in ['tailored-resume','questions','analyze','plan']: current=self.post(prefix+'/'+suffix)
        gate=self.client.get(ROOT+prefix+'/writer-readiness').json()
        self.assertEqual(gate['questions'][2]['status'],'READY')
        result=self.post(prefix+'/write',{'question_id':current['questions'][2]['id'],'ai_mode':'mock'})
        self.assertEqual(result['result']['status'],'READY')
        self.assertEqual(result['telemetry']['llm_calls'],0)
        self.assertTrue(result['result']['candidate']['sentences'][0]['support_refs'])

    def test_ownership_and_auth(self):
        first = self.app()
        other = Users.objects.create(firebase_uid='other-local', password='unused', role='student', is_active=True, must_change_password=False)
        token = issue_tokens(load_lms_user(other.firebase_uid))['access']
        self.client.defaults['HTTP_AUTHORIZATION'] = 'Bearer ' + token
        prefix = '/applications/' + first['id']
        self.assertEqual(self.client.get(ROOT + prefix).status_code, 404)
        for suffix in ['tailored-resume','questions','analyze','plan']:
            self.post(prefix + '/' + suffix, status=404)
        self.client.defaults.clear()
        self.assertEqual(self.client.get(ROOT + '/catalog').status_code, 401)

    def test_idempotent_seed_and_question_snapshot(self):
        before = (Resumes.objects.count(), ResumeExperiences.objects.count(), ResumeEvidence.objects.count())
        seed(); seed()
        self.assertEqual(before, (Resumes.objects.count(), ResumeExperiences.objects.count(), ResumeEvidence.objects.count()))
        prefix = '/applications/' + self.app()['id']
        original = self.post(prefix + '/questions')['questions']
        RecruitRoles.objects.filter(pk=self.role.pk).update(questions=[{'text': 'Changed source', 'order': 1}])
        self.assertEqual(original, self.client.get(ROOT + prefix).json()['questions'])

    def test_local_guard_and_nonlocal_exposure(self):
        import sys
        self.assertNotIn('lms_server', sys.modules)
        for host in ['db.rds.amazonaws.com', 'example.com', '::1', '127.0.0.1.evil', '']:
            with self.assertRaises(ImproperlyConfigured): require_loopback(host)
        for host in ['127.0.0.1', 'localhost']: self.assertEqual(require_loopback(host), host)
        with override_settings(LOCAL_RESUME_E2E=False):
            self.assertEqual(self.client.get(ROOT + '/catalog').status_code, 404)
            with self.assertRaises(RuntimeError): seed()

    def test_errors_are_safe_and_mock_default(self):
        response = self.post('/applications/open-or-create', {}, status=400)
        self.assertNotIn('Traceback', str(response))
        self.assertEqual(self.client.get(ROOT + '/catalog').json()['ai_mode'], 'mock')
        self.post('/login', {'email': EMAIL, 'password': 'wrong'}, status=401)

    def test_stale_plan_hidden_after_evidence_change(self):
        prefix = '/applications/' + self.app()['id']
        for step in ['questions', 'analyze', 'plan']: self.post(prefix + '/' + step)
        ResumeEvidence.objects.filter(source_id='local-e2e:exp-A-1').update(assertion_state='retracted')
        self.assertIsNone(self.client.get(ROOT + prefix).json()['planner'])
