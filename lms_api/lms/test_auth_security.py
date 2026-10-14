"""Security contracts without DB, network, or production Redis writes."""

from __future__ import annotations

from io import BytesIO
import json
import os
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth.hashers import make_password
from django.test import Client
from django.test import SimpleTestCase, override_settings
from pypdf import PdfWriter

from lms import auth_sessions
from lms.api import _record_bytes_match_type
from lms.commands import op_update_profile
from lms.jwt_auth import (
    AuthError, credential_fingerprint, issue_tokens, logout_refresh,
    rotate_refresh, user_from_access,
)


@override_settings(DEBUG=True)
class AuthSessionTests(SimpleTestCase):
    def setUp(self):
        auth_sessions._local.clear()
        self.user = {
            "id": 42, "firebase_uid": "test-uid", "role": "student", "is_active": True,
            "_credential_fingerprint": credential_fingerprint("stored-password-hash"),
        }
        self.load_patch = patch("lms.jwt_auth.load_lms_user", side_effect=lambda uid: dict(self.user) if uid == "test-uid" else None)
        self.load_patch.start()
        self.addCleanup(self.load_patch.stop)

    def test_refresh_rotates_atomically_and_old_refresh_cannot_win(self):
        first = issue_tokens(self.user)
        second = rotate_refresh(first["refresh"])
        with self.assertRaises(AuthError):
            rotate_refresh(first["refresh"])
        self.assertEqual("test-uid", user_from_access(second["access"])["firebase_uid"])

    def test_late_refresh_replay_revokes_session_family(self):
        first = issue_tokens(self.user)
        second = rotate_refresh(first["refresh"])
        with patch.object(auth_sessions.time, "time", return_value=auth_sessions.time.time() + 4):
            with self.assertRaises(AuthError):
                rotate_refresh(first["refresh"])
        with self.assertRaises(AuthError):
            user_from_access(second["access"])

    def test_logout_and_password_change_invalidate_old_tokens(self):
        first = issue_tokens(self.user)
        self.assertNotIn("_credential_fingerprint", user_from_access(first["access"]))
        logout_refresh(first["refresh"])
        with self.assertRaises(AuthError):
            user_from_access(first["access"])
        with self.assertRaises(AuthError):
            rotate_refresh(first["refresh"])

        second = issue_tokens(self.user)
        self.user["_credential_fingerprint"] = credential_fingerprint("new-password-hash")
        with self.assertRaises(AuthError):
            user_from_access(second["access"])
        with self.assertRaises(AuthError):
            rotate_refresh(second["refresh"])

    def test_logout_with_pre_rotation_token_revokes_same_session(self):
        first = issue_tokens(self.user)
        rotated = rotate_refresh(first["refresh"])
        logout_refresh(first["refresh"])
        with self.assertRaises(AuthError):
            user_from_access(rotated["access"])

    def test_login_limit_is_shared_keyed_by_account_and_ip(self):
        for _ in range(8):
            self.assertTrue(auth_sessions.login_attempt_allowed("student@example.test", "127.0.0.1"))
        self.assertFalse(auth_sessions.login_attempt_allowed("student@example.test", "127.0.0.1"))
        self.assertTrue(auth_sessions.login_attempt_allowed("other@example.test", "127.0.0.1"))

    def test_untrusted_forwarded_ip_is_ignored(self):
        request = SimpleNamespace(META={"REMOTE_ADDR": "192.0.2.10", "HTTP_X_FORWARDED_FOR": "203.0.113.1", "HTTP_X_LMS_CLIENT_IP": "203.0.113.2"})
        self.assertEqual("192.0.2.10", auth_sessions.client_ip(request))
        with patch.dict(os.environ, {"AUTH_TRUST_CLOUDFRONT_CLIENT_IP": "1", "AUTH_TRUSTED_PROXY_CIDRS": "192.0.2.0/24"}):
            self.assertEqual("203.0.113.2", auth_sessions.client_ip(request))
            request.META["REMOTE_ADDR"] = "198.51.100.10"
            self.assertEqual("198.51.100.10", auth_sessions.client_ip(request))

    @override_settings(DEBUG=False)
    def test_redis_outage_fails_closed(self):
        with patch.object(auth_sessions, "_redis", side_effect=ConnectionError("offline")):
            with self.assertRaises(auth_sessions.SessionUnavailable):
                auth_sessions.session_active("sid", "uid")
            with self.assertRaises(auth_sessions.SessionUnavailable):
                auth_sessions.login_attempt_allowed("a@example.test", "192.0.2.1")


class ProfileAndUploadTests(SimpleTestCase):
    def test_profile_cannot_change_password_or_authentication_state(self):
        for role in ("student", "admin"):
            user = {"firebase_uid": "user-1", "role": role}
            for forbidden in ("password", "mustChangePassword", "lastLoginAt"):
                with self.subTest(role=role, forbidden=forbidden), self.assertRaises(ValueError):
                    op_update_profile(None, user, {forbidden: "anything"})

    def test_record_evidence_rejects_mime_spoofing_and_accepts_real_pdf(self):
        self.assertFalse(_record_bytes_match_type(b"not a PDF", "application/pdf"))
        self.assertFalse(_record_bytes_match_type(b"%PDF-1.7\nnot a complete PDF", "application/pdf"))
        self.assertFalse(_record_bytes_match_type(b"plain text", "image/png"))
        writer = PdfWriter()
        writer.add_blank_page(width=72, height=72)
        stream = BytesIO()
        writer.write(stream)
        self.assertTrue(_record_bytes_match_type(stream.getvalue(), "application/pdf"))


@override_settings(DEBUG=True)
class AuthHttpContractTests(SimpleTestCase):
    def setUp(self):
        auth_sessions._local.clear()
        self.client = Client()

    def test_unknown_and_wrong_password_have_same_response(self):
        class Cursor:
            description = [(name,) for name in ("id", "firebase_uid", "email", "password", "role", "is_active", "must_change_password")]

            def __init__(self, row):
                self.row = row

            def __enter__(self):
                return self

            def __exit__(self, *_):
                return False

            def execute(self, *_):
                pass

            def fetchall(self):
                return [self.row] if self.row else []

        body = json.dumps({"email": "someone@example.test", "password": "wrong"})
        responses = []
        for row in (None, (1, "uid", "someone@example.test", make_password("right"), "student", True, False)):
            with patch("lms.api.connection", SimpleNamespace(cursor=lambda: Cursor(row))), patch("lms.api.login_attempt_allowed", return_value=True):
                responses.append(self.client.post("/api/login", body, content_type="application/json"))
        self.assertEqual(400, responses[0].status_code)
        self.assertEqual(responses[0].json(), responses[1].json())

    def test_me_never_exposes_credential_fingerprint_and_logout_revokes(self):
        user = {"id": 42, "firebase_uid": "uid", "role": "student", "is_active": True,
                "_credential_fingerprint": credential_fingerprint("stored-hash")}
        with patch("lms.jwt_auth.load_lms_user", side_effect=lambda _uid: dict(user)):
            tokens = issue_tokens(user)
            response = self.client.get("/api/me", HTTP_AUTHORIZATION="Bearer " + tokens["access"])
            self.assertEqual(200, response.status_code)
            self.assertNotIn("_credential_fingerprint", response.json())
            logout = self.client.post("/api/logout", json.dumps({"refresh": tokens["refresh"]}), content_type="application/json")
            self.assertEqual(200, logout.status_code)
            self.assertEqual(401, self.client.get("/api/me", HTTP_AUTHORIZATION="Bearer " + tokens["access"]).status_code)
