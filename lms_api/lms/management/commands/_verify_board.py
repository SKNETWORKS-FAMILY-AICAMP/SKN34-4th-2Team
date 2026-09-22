"""One-shot verify. Do not print secrets."""

from django.core.management.base import BaseCommand
from django.db import connection
from django.test import Client


class Command(BaseCommand):
    help = "Verify scheduled notice + alert popup student visibility"

    def handle(self, *args, **options):
        client = Client()
        with connection.cursor() as cur:
            cur.execute(
                "SELECT role, COUNT(*) FROM users WHERE is_active GROUP BY role ORDER BY role"
            )
            self.stdout.write(f"roles={dict(cur.fetchall())}")
            cur.execute(
                "SELECT email, role FROM users WHERE is_active AND role IN ('admin','student') ORDER BY role"
            )
            rows = cur.fetchall()
        admin = next(email for email, role in rows if role == "admin")
        student = next(email for email, role in rows if role == "student")
        login = client.post(
            "/api/login",
            {"email": admin, "password": "x"},
            content_type="application/json",
        )
        body = login.json()
        self.stdout.write(f"admin_login={login.status_code} ok={body.get('ok')} role={body.get('role')}")
        created = client.post(
            "/api/scheduled-notices",
            {
                "title": "verify-scheduled",
                "content": "from-api",
                "repeatType": "once",
                "publishTime": "00:00",
                "isActive": True,
            },
            content_type="application/json",
        )
        self.stdout.write(f"scheduled_create={created.status_code} {created.json()}")
        sid = created.json().get("id")
        popup = client.post(
            "/api/alert-popups",
            {"title": "verify-popup", "content": "hello-student", "isActive": True},
            content_type="application/json",
        )
        self.stdout.write(f"popup_create={popup.status_code} {popup.json()}")
        published = client.post(
            "/api/scheduled-notices/publish",
            {"ids": [sid]},
            content_type="application/json",
        )
        self.stdout.write(f"publish={published.status_code} {published.json()}")
        boot = client.get("/api/bootstrap").json()
        self.stdout.write(
            "admin_boot notices={0} scheduled={1} popups={2}".format(
                len(boot.get("notices") or []),
                len(boot.get("scheduledNotices") or []),
                len(boot.get("alertPopups") or []),
            )
        )
        client.post("/api/logout", {}, content_type="application/json")
        student_login = client.post(
            "/api/login",
            {"email": student, "password": "x"},
            content_type="application/json",
        )
        self.stdout.write(
            f"student_login={student_login.status_code} ok={student_login.json().get('ok')} role={student_login.json().get('role')}"
        )
        student_boot = client.get("/api/bootstrap").json()
        notice_ok = any(n.get("title") == "verify-scheduled" for n in (student_boot.get("notices") or []))
        popup_ok = any(
            p.get("title") == "verify-popup" and p.get("isActive")
            for p in (student_boot.get("alertPopups") or [])
        )
        self.stdout.write(
            f"student_has_notice={notice_ok} student_has_popup={popup_ok} student_scheduled_len={len(student_boot.get('scheduledNotices') or [])}"
        )
