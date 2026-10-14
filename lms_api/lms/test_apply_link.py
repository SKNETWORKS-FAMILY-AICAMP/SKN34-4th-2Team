"""홈페이지 지원 공고의 회사 채용 사이트 주소 — 사람인 · 잡코리아 페이지에서 꺼낸다."""

from unittest import TestCase

from django.test import Client, SimpleTestCase

from lms.apply_link import find_homepage, homepage_from_jobkorea, homepage_from_saramin, page_for

# 잡코리아 상세 페이지는 데이터를 문자열 속 JSON 으로 싣는다(2026-09-30 이마트 공고에서 옮김)
JOBKOREA_PAGE = (
    r'\"recruitment\":{\"workFields\":[\"홈페이지 지원\"]},\"reception\":{\"receptionOptions\":'
    r'[{\"type\":\"HOMEPAGE\",\"contents\":[\"https://job.shinsegae.com/rcrut/detail/5365\"]}],\"resumeDocuments\":[]}'
)
SARAMIN_PAGE = '<script type="text/javascript">document.location.replace("https://recruit.cj.net/");</script>'


class ParseTests(TestCase):
    def test_jobkorea_reception_option(self):
        self.assertEqual(homepage_from_jobkorea(JOBKOREA_PAGE), "https://job.shinsegae.com/rcrut/detail/5365")
        self.assertIsNone(homepage_from_jobkorea(r'{\"type\":\"ONLINE\",\"contents\":[]}'), "사이트 입사지원")

    def test_saramin_redirect(self):
        self.assertEqual(homepage_from_saramin(SARAMIN_PAGE), "https://recruit.cj.net/")
        self.assertEqual(homepage_from_saramin("<script>location.href = 'https://careers.example.com/a'</script>"),
                         "https://careers.example.com/a")

    def test_only_http_addresses_are_passed_to_the_browser(self):
        self.assertIsNone(homepage_from_saramin('document.location.replace("javascript:alert(1)")'))
        self.assertIsNone(homepage_from_saramin(""))

    def test_pages_by_job_id(self):
        self.assertEqual(page_for("JOBKOREA-50048715")[0], "https://www.jobkorea.co.kr/Recruit/GI_Read/50048715")
        self.assertIn("render-homepage?rec_idx=55101818", page_for("SARAMIN-55101818")[0])
        self.assertIsNone(page_for("MANUAL-abc"))


class FindTests(TestCase):
    def test_jobkorea_copy_first(self):
        pages = {
            "https://www.jobkorea.co.kr/Recruit/GI_Read/2": JOBKOREA_PAGE,
            "https://www.saramin.co.kr/zf_user/track-apply-form/render-homepage?rec_idx=1": SARAMIN_PAGE,
        }
        opened = []

        def fetch(url):
            opened.append(url)
            return pages.get(url)

        self.assertEqual(find_homepage(["SARAMIN-1", "JOBKOREA-2"], fetch),
                         ("https://job.shinsegae.com/rcrut/detail/5365", "JOBKOREA-2"))
        self.assertEqual(len(opened), 1, "잡코리아에서 찾았으면 사람인은 열지 않는다")

    def test_falls_back_to_saramin_then_none(self):
        fetch = {"https://www.saramin.co.kr/zf_user/track-apply-form/render-homepage?rec_idx=1": SARAMIN_PAGE}.get
        self.assertEqual(find_homepage(["SARAMIN-1", "JOBKOREA-2"], fetch), ("https://recruit.cj.net/", "SARAMIN-1"))
        self.assertIsNone(find_homepage(["SARAMIN-9"], lambda url: None))


class RouteTests(SimpleTestCase):
    def test_needs_login(self):
        client = Client(HTTP_HOST="127.0.0.1")
        self.assertEqual(client.get("/api/postings/SARAMIN-1/apply-link").status_code, 401)
