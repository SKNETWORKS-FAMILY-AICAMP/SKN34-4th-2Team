"""Authenticated thread forwarding and invalid IDs, with no upstream request."""
import json
import os
from unittest.mock import patch
from django.test import Client, SimpleTestCase


class ChatThreadTests(SimpleTestCase):
    def call(self, path, thread=None, role='student'):
        user = {'id': 1, 'firebase_uid': 'synthetic-user', 'role': role,
                'is_active': True, 'must_change_password': False}
        payload = {'message': 'synthetic'}
        if thread is not None:
            payload['threadId'] = thread
        with patch('lms.middleware.user_from_access', return_value=user), \
             patch.dict(os.environ, {'CHATBOT_URL': 'http://ai.invalid', 'LMS_AI_SHARED_TOKEN': 'synthetic-token'}), \
             patch('lms.api.urllib.request.urlopen') as upstream:
            upstream.return_value.__enter__.return_value.read.return_value = b'{"answer":"synthetic"}'
            response = Client().post(path, json.dumps(payload), content_type='application/json',
                                     HTTP_AUTHORIZATION='Bearer synthetic')
        return response, upstream

    def test_valid_thread_and_legacy_default_forward_server_uid(self):
        for path in ('/api/chat', '/api/chat/stream'):
            for thread in (None, 'conversation-123'):
                response, upstream = self.call(path, thread)
                self.assertEqual(response.status_code, 200)
                request = upstream.call_args.args[0]
                sent = json.loads(request.data)
                self.assertEqual(sent['thread_id'], thread or 'web')
                self.assertEqual(sent['uid'], 'synthetic-user')
                response.close()

    def test_invalid_thread_is_rejected_before_upstream(self):
        for value in ('', '../../other', 'x' * 81):
            response, upstream = self.call('/api/chat', value)
            self.assertEqual(response.status_code, 422)
            upstream.assert_not_called()

    def test_existing_student_permission_is_preserved(self):
        response, upstream = self.call('/api/chat', 'conversation-123', role='admin')
        self.assertEqual(response.status_code, 403)
        upstream.assert_not_called()
