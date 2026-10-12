"""Exercise Ninja request parsing, including the atomic view wrapper, without DB writes."""
from unittest.mock import patch
from django.contrib.auth.hashers import make_password, check_password
from django.test import SimpleTestCase, Client


class PasswordHttpTests(SimpleTestCase):
    def request(self, current, new_password):
        user = {'id': 100, 'firebase_uid': 'password-http-fixture',
                'role': 'student', 'is_active': True, 'must_change_password': True}
        with patch('lms.middleware.user_from_access', return_value=user), \
             patch('django.db.transaction.Atomic.__enter__'), \
             patch('django.db.transaction.Atomic.__exit__', return_value=False), \
             patch('lms.api.connection') as connection, \
             patch('lms.api.load_lms_user', return_value=user), \
             patch('lms.api.issue_tokens', return_value={'access': 'new-test-access', 'refresh': 'new-test-refresh'}):
            cursor = connection.cursor.return_value.__enter__.return_value
            cursor.fetchone.return_value = (make_password('InitialTest123!'), True)
            response = Client().post('/api/password',
                {'currentPassword': current, 'newPassword': new_password},
                content_type='application/json', HTTP_AUTHORIZATION='Bearer fixture')
            return response, cursor.execute.call_args_list

    def test_valid_password_body_reaches_atomic_handler_and_returns_tokens(self):
        response, calls = self.request('InitialTest123!', 'ReplacementTest456!')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['ok'])
        self.assertEqual(response.json()['access'], 'new-test-access')
        updates = [call for call in calls if 'UPDATE users' in call.args[0]]
        self.assertEqual(len(updates), 1)
        self.assertTrue(check_password('ReplacementTest456!', updates[0].args[1][0]))

    def test_wrong_current_password_never_writes(self):
        response, calls = self.request('IncorrectTest123!', 'ReplacementTest456!')
        self.assertEqual(response.status_code, 400)
        self.assertFalse(any('UPDATE users' in call.args[0] for call in calls))

    def test_short_password_is_validation_error_not_server_error(self):
        response, calls = self.request('InitialTest123!', 'short')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(calls, [])
