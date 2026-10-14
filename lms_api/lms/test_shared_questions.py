"""자소서 문항 공유 — 직무 이름 접기 · 문항 비교 · 공유 흐름(테스트 DB)."""

from unittest import skipUnless

from django.db import connection
from django.test import SimpleTestCase, TestCase

from lms import shared_questions as sq
from lms.models import RecruitRoles, Users

Q1 = [{"question": "1. 지원한 직무에 관심을 갖게 된 계기를 기술해 주십시오. (700자)", "limit": 700},
      {"question": "2. 협업 경험을 작성해 주십시오.", "limit": 500}]
Q1_AGAIN = [{"question": "지원한 직무에 관심을 갖게 된 계기를 기술해 주십시오", "limit": 700},
            {"question": "협업 경험을 작성해 주십시오", "limit": 500}]
Q2 = [{"question": "생산 현장의 문제를 개선한 경험을 작성해 주십시오.", "limit": 700}]


class RoleAndQuestionKeyTests(SimpleTestCase):
    def test_role_names_that_mean_the_same_role(self):
        same = ["SW 개발", "SW개발", "sw 개발 직무", "소프트웨어 개발", "SW 개발자", "SW 개발 분야"]
        self.assertEqual({sq.role_key(name) for name in same}, {"sw개발"})
        self.assertEqual(sq.role_key("AI 엔지니어"), sq.role_key("인공지능 개발자"))
        self.assertNotEqual(sq.role_key("생산기술"), sq.role_key("SW 개발"))
        self.assertEqual(sq.role_key("직무"), "직무", "꼬리말만 남은 이름은 지우지 않는다")

    def test_questions_differ_only_by_number_limit_or_spacing(self):
        self.assertEqual(sq.questions_key(sq.clean_questions(Q1)), sq.questions_key(sq.clean_questions(Q1_AGAIN)))
        self.assertNotEqual(sq.questions_key(sq.clean_questions(Q1)), sq.questions_key(sq.clean_questions(Q2)))

    def test_clean_questions_drops_blank_and_keeps_limits(self):
        cleaned = sq.clean_questions([{"question": "  ", "limit": 3}, {"question": "지원 동기", "limit": 600},
                                      {"question": "포부", "limit": None}])
        self.assertEqual(cleaned, [{"order": 1, "text": "지원 동기", "character_limit": 600}, {"order": 2, "text": "포부"}])


@skipUnless(connection.vendor == "postgresql", "jobs 스키마는 PostgreSQL")
class SharedQuestionFlowTests(TestCase):
    def setUp(self) -> None:
        self.a, self.b, self.c = (
            Users.objects.create(password="x", display_name=n, role="student", is_active=True, must_change_password=False)
            for n in "abc"
        )
        with connection.cursor() as cur:
            for job_id, title in (("J1", "2026 하반기 SW 직군 신입사원 채용"), ("J2", "[2026 하반기] 생산기술 신입 채용")):
                cur.execute(
                    """INSERT INTO jobs.jobs (job_id, source, source_job_id, company, title, first_seen_at, last_seen_at)
                       VALUES (%s, 'SARAMIN_POC', %s, '(주)현대모비스', %s, now(), now())""",
                    [job_id, job_id, title],
                )

    def test_shared_with_everyone_merged_by_role_and_by_questions(self):
        first = sq.save(self.a.pk, "J1", "SW 개발", Q1, share=True)
        self.assertTrue(first["created"])
        # 다른 공고(J2)라도 같은 회사 · 시즌이면 보인다
        seen = sq.list_shared(self.b.pk, "J2")
        self.assertEqual((seen["company"], seen["season"]), ("(주)현대모비스", "2026 하반기"))
        self.assertEqual([r["name"] for r in seen["roles"]], ["SW 개발"])
        # 꼬리말만 다른 직무 · 번호만 다른 문항 → 새로 만들지 않고 그 정리를 쓴 것으로
        again = sq.save(self.b.pk, "J1", "SW개발 직무", Q1_AGAIN, share=True)
        self.assertEqual((again["id"], again["created"], again["roleName"]), (first["id"], False, "SW 개발"))
        self.assertEqual(RecruitRoles.objects.get(pk=first["id"]).use_count, 1)
        # 같은 직무 다른 문항은 같은 칩 아래 두 번째 정리
        sq.save(self.c.pk, "J1", "소프트웨어 개발", Q2, share=True)
        [role] = sq.list_shared(self.b.pk, "J1")["roles"]
        self.assertEqual(role["names"], ["SW 개발"])
        self.assertEqual([s["useCount"] for s in role["sets"]], [1, 0])

    def test_not_shared_is_seen_only_by_its_owner(self):
        sq.save(self.c.pk, "J1", "SW 개발", Q1, share=False)
        self.assertEqual(sq.list_shared(self.b.pk, "J1")["roles"], [])
        self.assertEqual(len(sq.list_shared(self.c.pk, "J1")["roles"]), 1)

    def test_same_questions_under_another_name_is_asked_before_saving(self):
        sq.save(self.a.pk, "J1", "백엔드", Q1, share=True)
        self.assertEqual(sq.check(self.b.pk, "J1", "서버 개발", Q1_AGAIN)["sameRole"]["name"], "백엔드")
        self.assertIsNone(sq.check(self.b.pk, "J1", "서버 개발", Q2)["sameRole"])
        self.assertIsNone(sq.check(self.b.pk, "J1", "백엔드", Q1)["sameRole"], "같은 직무면 묻지 않는다")

    def test_common_questions_are_shown_apart_from_roles(self):
        sq.save(self.a.pk, "J1", sq.COMMON_ROLE, Q2, share=True)
        seen = sq.list_shared(self.b.pk, "J1")
        self.assertEqual(seen["roles"], [])
        self.assertEqual(len(seen["common"]), 1)

    def test_use_is_not_counted_for_the_author(self):
        saved = sq.save(self.a.pk, "J1", "SW 개발", Q1, share=True)
        sq.use(self.a.pk, saved["id"])
        sq.use(self.b.pk, saved["id"])
        self.assertEqual(RecruitRoles.objects.get(pk=saved["id"]).use_count, 1)

    def test_two_reports_hide_the_set_except_from_its_author(self):
        saved = sq.save(self.a.pk, "J1", "SW 개발", Q1, share=True)
        self.assertTrue(sq.list_shared(self.b.pk, "J1")["canReport"])
        self.assertEqual(sq.report(self.b.pk, saved["id"], "wrong"), {"hidden": False})
        self.assertEqual(sq.report(self.b.pk, saved["id"], "wrong"), {"hidden": False}, "한 학생은 한 번만 센다")
        self.assertEqual(sq.report(self.c.pk, saved["id"], "other_company"), {"hidden": True})
        self.assertEqual(sq.list_shared(self.b.pk, "J1")["roles"], [])
        self.assertEqual(len(sq.list_shared(self.a.pk, "J1")["roles"]), 1, "올린 학생에게는 보인다")
        with self.assertRaises(sq.SharedQuestionError):
            sq.report(self.b.pk, saved["id"], "no_reason")
