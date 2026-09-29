"""공고 링크 → job_id. 공고 맞춤 지원 화면이 붙여 넣은 주소로 공고를 찾는다."""

import urllib.error
from unittest import TestCase
from unittest.mock import patch

from django.test import Client, SimpleTestCase

from lms.posting_link import job_id_from_link


class JobIdFromLinkTests(TestCase):
    def test_saramin_pc_relay_and_mobile(self):
        self.assertEqual(
            job_id_from_link("https://www.saramin.co.kr/zf_user/jobs/relay/view?view_type=list&rec_idx=48123456&utm_source=x"),
            "SARAMIN-48123456",
        )
        self.assertEqual(job_id_from_link("https://www.saramin.co.kr/zf_user/jobs/view?rec_idx=48123456"), "SARAMIN-48123456")
        self.assertEqual(job_id_from_link("m.saramin.co.kr/job-search/view?rec_idx=48123456"), "SARAMIN-48123456")

    def test_jobkorea_detail_iframe_and_mobile(self):
        self.assertEqual(
            job_id_from_link("https://www.jobkorea.co.kr/Recruit/GI_Read/46512345?Oem_Code=C1&logpath=1"),
            "JOBKOREA-46512345",
        )
        self.assertEqual(job_id_from_link("https://m.jobkorea.co.kr/Recruit/GI_Read/46512345"), "JOBKOREA-46512345")
        self.assertEqual(
            job_id_from_link("https://www.jobkorea.co.kr/Recruit/GI_Read_Comt_Ifrm?Gno=46512345"),
            "JOBKOREA-46512345",
        )

    def test_rejects_other_sites_and_missing_numbers(self):
        self.assertIsNone(job_id_from_link(""))
        self.assertIsNone(job_id_from_link("https://www.wanted.co.kr/wd/12345"))
        self.assertIsNone(job_id_from_link("https://www.saramin.co.kr/zf_user/jobs/list"))
        self.assertIsNone(job_id_from_link("https://www.saramin.co.kr/zf_user/jobs/view?rec_idx=abc"))
        self.assertIsNone(job_id_from_link("https://evil-saramin.co.kr/view?rec_idx=1"))


class PostingLinkRouteTests(SimpleTestCase):
    def test_link_lookup_and_requirements_need_login(self):
        client = Client(HTTP_HOST="127.0.0.1")
        self.assertEqual(client.get("/api/posting-link", {"url": "https://www.saramin.co.kr/x?rec_idx=1"}).status_code, 401)
        response = client.post("/api/resume-review/requirements", data='{"jobId": "SARAMIN-1"}', content_type="application/json")
        self.assertEqual(response.status_code, 401)
        response = client.post(
            "/api/resume-review/question-answer",
            data='{"resumeId": "r1", "tailoredResumeId": "t1", "questionId": "cq1"}',
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 401)


class PostingLinkVerifyTests(SimpleTestCase):
    """REMOVED 는 목록에서 안 보였다는 뜻일 뿐 — 링크로 불러오면 페이지를 열어 확인한다."""

    URL = "https://www.saramin.co.kr/zf_user/jobs/view?rec_idx=1"

    def lookup(self, rows, alive):
        from lms import api

        rows = list(rows)
        with patch.object(api, "_require_user"), patch.object(
            api, "job_posting", side_effect=lambda _request, _job_id: rows.pop(0)
        ), patch.object(api, "_verify_posting", return_value=alive) as verify:
            return api.posting_by_link(None, url=self.URL), verify

    def test_removed_but_alive_is_read_again_as_open(self):
        found, verify = self.lookup([{"status": "REMOVED"}, {"status": "OPEN"}], alive=True)
        self.assertEqual(found["status"], "OPEN")
        verify.assert_called_once_with("SARAMIN-1")

    def test_removed_and_closed_on_the_page_is_shown_as_closed(self):
        found, _ = self.lookup([{"status": "REMOVED"}], alive=False)
        self.assertEqual(found["status"], "CLOSED")

    def test_unverified_removed_stays_removed(self):
        found, _ = self.lookup([{"status": "REMOVED"}], alive=None)
        self.assertEqual(found["status"], "REMOVED")

    def test_expired_is_rechecked_because_deadlines_get_extended(self):
        found, verify = self.lookup([{"status": "EXPIRED"}, {"status": "OPEN"}], alive=True)
        self.assertEqual(found["status"], "OPEN")
        verify.assert_called_once_with("SARAMIN-1")

    def test_open_and_closed_are_not_rechecked(self):
        for status in ("OPEN", "CLOSED"):
            found, verify = self.lookup([{"status": status}], alive=True)
            self.assertEqual(found["status"], status)
            verify.assert_not_called()


class QuestionExtractRouteTests(SimpleTestCase):
    """캡처 → 문항: 로그인 · 이미지 종류 · 장수를 Django 가 먼저 막는다. 이미지는 저장하지 않고 넘기기만 한다."""

    def upload(self, *files):
        from django.core.files.uploadedfile import SimpleUploadedFile

        from lms import api

        request = type("Req", (), {})()
        with patch.object(api, "_require_user"), patch.object(api, "_review_call", return_value={"questions": []}) as call:
            result = api.resume_review_question_extract(
                request, [SimpleUploadedFile(name, data, content_type=kind) for name, data, kind in files]
            )
        return result, call

    def test_needs_login(self):
        response = Client(HTTP_HOST="127.0.0.1").post("/api/resume-review/question-extract")
        self.assertEqual(response.status_code, 401)

    def test_images_are_sent_as_data_urls(self):
        result, call = self.upload(("a.png", b"PNG", "image/png"))
        self.assertEqual(result, {"questions": []})
        path, payload = call.call_args.args
        self.assertEqual(path, "/api/v1/resumes/question-extract/proxy")
        self.assertEqual(payload["images"], ["data:image/png;base64,UE5H"])

    def test_takes_one_pdf_but_not_with_other_files(self):
        result, call = self.upload(("form.pdf", b"%PDF", "application/pdf"))
        self.assertEqual(result, {"questions": []})
        self.assertEqual(call.call_args.args[1]["images"], ["data:application/pdf;base64,JVBERg=="])
        result, call = self.upload(("form.pdf", b"%PDF", "application/pdf"), ("a.png", b"PNG", "image/png"))
        self.assertEqual(result.status_code, 400)
        call.assert_not_called()

    def test_rejects_word_and_too_many(self):
        result, call = self.upload(("form.docx", b"PK", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"))
        self.assertEqual(result.status_code, 400)
        call.assert_not_called()
        result, call = self.upload(*[(f"{i}.png", b"x", "image/png") for i in range(4)])
        self.assertEqual(result.status_code, 400)


class QuestionLinkTests(SimpleTestCase):
    """첨부 양식 링크 — 서버가 대신 여는 주소라 사람인 · 잡코리아만, 넘겨 가는 곳도 같은 규칙."""

    def read(self, url, body=b"%PDF-1.4 ...", fail=None):
        from io import BytesIO

        from lms import api
        from lms.api import QuestionLinkIn

        opened = []

        class Opener:
            def open(self, req, timeout):
                opened.append(req.full_url)
                if fail is not None:
                    raise fail
                return BytesIO(body)

        with patch.object(api, "_require_user"), patch.object(api, "_ATTACHMENT_OPENER", Opener()), patch.object(
            api, "_review_call", return_value={"questions": []}
        ) as call:
            result = api.resume_review_question_extract_link(None, QuestionLinkIn(url=url))
        return result, call, opened

    def test_saramin_pdf_is_read(self):
        url = "https://dym-upload.saramin.co.kr/upload/dym2_5/55/3987/filedown/2026-09-11/attach5.pdf"
        result, call, opened = self.read(url)
        self.assertEqual(result, {"questions": []})
        self.assertEqual(opened, [url])
        self.assertTrue(call.call_args.args[1]["images"][0].startswith("data:application/pdf;base64,"))

    def test_other_hosts_plain_http_and_lookalikes_are_not_opened(self):
        for url in (
            "https://example.com/form.pdf",
            "http://dym-upload.saramin.co.kr/a.pdf",
            "https://saramin.co.kr.attacker.com/a.pdf",
            "https://169.254.169.254/latest/meta-data",
        ):
            result, call, opened = self.read(url)
            self.assertEqual(result.status_code, 400, url)
            self.assertEqual(opened, [], url)
            call.assert_not_called()

    def test_redirect_out_of_the_allowed_hosts_is_refused(self):
        from lms.api import _AllowedRedirects

        handler = _AllowedRedirects()
        with self.assertRaises(urllib.error.HTTPError):
            handler.redirect_request(None, None, 302, "Found", {}, "http://127.0.0.1:8000/admin")

    def test_non_pdf_body_is_refused(self):
        result, call, _ = self.read("https://file.jobkorea.co.kr/form.hwp", body=b"\xd0\xcf\x11\xe0 hwp")
        self.assertEqual(result.status_code, 400)
        call.assert_not_called()
