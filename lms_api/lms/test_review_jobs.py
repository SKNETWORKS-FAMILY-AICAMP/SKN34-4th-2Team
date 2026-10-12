import json
from unittest.mock import patch

from django.test import SimpleTestCase
from ninja.responses import Response
from lms import review_jobs as jobs


class MemoryStore:
    def __init__(self):
        self.data = {}

    def set(self, key, value, nx=False, ex=None):
        if nx and key in self.data:
            return False
        self.data[key] = value
        return True

    def get(self, key):
        return self.data.get(key)

    def delete(self, key):
        self.data.pop(key, None)

    def eval(self, script, count, key, token):
        if self.get(key) == token:
            self.delete(key)


class ReviewJobTests(SimpleTestCase):
    def setUp(self):
        self.db = MemoryStore()
        self.patch = patch.object(jobs, 'store', return_value=self.db)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.payload = {'uid': 'student-a', 'resume_id': '33', 'request_id': 'initial'}

    def queue(self):
        with patch.object(jobs.run_review_job, 'apply_async') as enqueue:
            first = jobs.submit_or_poll(self.payload, 'attempt')
            second = jobs.submit_or_poll(self.payload, 'attempt')
        self.assertEqual(enqueue.call_count, 1)
        self.assertEqual(first['async_job']['state'], 'queued')
        self.assertEqual(second['async_job']['state'], 'queued')
        return jobs.job_key(self.payload, 'attempt')

    def test_polling_does_not_enqueue_again_or_cross_identity(self):
        self.queue()
        other = {**self.payload, 'uid': 'student-b'}
        self.assertNotEqual(jobs.job_key(other, 'attempt'), jobs.job_key(self.payload, 'attempt'))

    def test_worker_continues_checkpoints_and_returns_only_final_response(self):
        key = self.queue()
        def response(state, stage):
            return {'review_id': 'canonical', 'telemetry': {'execution': {'state': state, 'stage': stage}}}
        final = response('verified', 'done')
        final['sentence_reviews'] = [{'validation_status': 'READY'}]
        with patch('lms.api._review_call', side_effect=[response('analyzed', 'write'), response('verification_pending', 'verify'), final]) as call:
            jobs.run_review_job.run(key, self.payload)
        self.assertEqual(call.call_count, 3)
        self.assertEqual(call.call_args_list[1].args[1]['request_id'], 'canonical')
        self.assertEqual(jobs.submit_or_poll(self.payload, 'attempt'), final)
        with patch('lms.api._review_call') as call:
            jobs.run_review_job.run(key, self.payload)
            call.assert_not_called()

    def test_verifier_timeout_is_pending_not_success_and_does_not_rewrite(self):
        key = self.queue()
        pending = {'review_id': 'canonical', 'sentence_reviews': [], 'telemetry': {'execution': {
            'state': 'verification_pending', 'stage': 'verify', 'retryable_error': 'verification_unavailable'}}}
        with patch('lms.api._review_call', return_value=pending) as call:
            jobs.run_review_job.run(key, self.payload)
        self.assertEqual(call.call_count, 1)
        self.assertEqual(jobs.submit_or_poll(self.payload, 'attempt'), pending)

    def test_failure_stays_failure_and_busy_reuses_request(self):
        key = self.queue()
        with patch('lms.api._review_call', side_effect=[Response({'detail': 'review_stage_busy'}, status=409), Response({'detail': 'input_changed'}, status=409)]) as call, patch.object(jobs.time, 'sleep'):
            jobs.run_review_job.run(key, self.payload)
        self.assertEqual(call.call_count, 2)
        result = jobs.submit_or_poll(self.payload, 'attempt')
        self.assertEqual(result.status_code, 409)
        self.assertEqual(json.loads(result.content)['detail'], 'input_changed')

    def test_redelivery_resumes_saved_canonical_checkpoint(self):
        key = self.queue()
        self.db.set(key, json.dumps({'state': 'running', 'continuation': {**self.payload, 'request_id': 'canonical'}}))
        with patch('lms.api._review_call', return_value={'review_id': 'canonical'}) as call:
            jobs.run_review_job.run(key, self.payload)
        self.assertEqual(call.call_args.args[1]['request_id'], 'canonical')

