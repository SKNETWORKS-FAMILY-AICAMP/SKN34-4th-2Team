"""앱 푸시 — 토큰 검사, 커밋 뒤 발송, 만료 토큰 정리"""

from unittest import TestCase
from unittest.mock import MagicMock, patch

from django.test import Client, SimpleTestCase

from lms import push


class PushTokenRouteTests(SimpleTestCase):
    def test_register_requires_login(self):
        response = Client(HTTP_HOST="127.0.0.1").post(
            "/api/push-tokens", data='{"token": "ExponentPushToken[abc]"}', content_type="application/json",
        )
        self.assertEqual(response.status_code, 401)


class PushTests(TestCase):
    def test_expo_token_shape(self):
        self.assertTrue(push.is_expo_token("ExponentPushToken[abc]"))
        self.assertTrue(push.is_expo_token("ExpoPushToken[abc]"))
        self.assertFalse(push.is_expo_token("fcm-raw-token"))

    def test_notify_waits_for_commit_and_dedupes(self):
        with patch("lms.push.connection") as conn, \
             patch("lms.push.transaction.on_commit") as on_commit, \
             patch("lms.push.threading.Thread") as thread:
            conn.in_atomic_block = True
            push.notify_users([3, 3, None, 5], "제목", "  여러\n줄  본문 ", "/(student)/attendance")
            thread.assert_not_called()
            on_commit.call_args[0][0]()
        args = thread.call_args.kwargs["args"]
        self.assertEqual(args, ([3, 5], "제목", "여러 줄 본문", "/(student)/attendance"))

    def test_notify_outside_transaction_sends_now(self):
        with patch("lms.push.connection") as conn, \
             patch("lms.push.transaction.on_commit") as on_commit, \
             patch("lms.push.threading.Thread") as thread:
            conn.in_atomic_block = False
            push.notify_users([1], "t", "b")
        on_commit.assert_not_called()
        thread.assert_called_once()

    def test_disabled_sends_nothing(self):
        with patch.dict("os.environ", {"LMS_PUSH_ENABLED": "0"}), patch("lms.push.transaction.on_commit") as on_commit:
            push.notify_users([1], "t", "b")
        on_commit.assert_not_called()

    def test_send_removes_unregistered_devices(self):
        cursor = MagicMock()
        cursor.__enter__.return_value = cursor
        tickets = [{"status": "ok"}, {"status": "error", "details": {"error": "DeviceNotRegistered"}}]
        with patch("lms.push._tokens_for", return_value=["ExpoPushToken[a]", "ExpoPushToken[b]"]), \
             patch("lms.push._post", return_value=tickets) as post, \
             patch("lms.push.connection") as conn:
            conn.cursor.return_value = cursor
            push._send([1, 2], "t", "b", "/x")
        sent = post.call_args[0][0]
        self.assertEqual([m["to"] for m in sent], ["ExpoPushToken[a]", "ExpoPushToken[b]"])
        self.assertEqual(sent[0]["data"], {"url": "/x"})
        cursor.execute.assert_called_once_with("DELETE FROM push_tokens WHERE token = ANY(%s)", [["ExpoPushToken[b]"]])
