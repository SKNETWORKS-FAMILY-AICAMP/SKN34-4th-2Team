"""잡코리아 차단 판정 — 2026-09-30 01시 차단 안내 페이지 370건이 공고 본문으로 저장된 일."""

import json
import tempfile
import unittest
from pathlib import Path

import requests

from job_matching_bot.crawling.http_session import BlockedByTargetSiteError
from job_matching_bot.crawling.jobkorea import check_response, read_done_ids
from job_matching_bot.sync import validate

# 그날 받은 안내 페이지의 글(앞부분). 응답 헤더에 charset 이 없었다.
BLOCK_PAGE = (
    "<html><body><h1>보안정책 서비스 이용 안내</h1>"
    "<p>현재 보안 정책에 따라 고객님의 접속이 일시적으로 제한되었습니다.</p>"
    "<p>이메일: helpdesk@albamon.com</p><p>ⓒ JOBKOREA LLC. All Rights Reserved.</p></body></html>"
)


def _response(html: str, content_type: str, status: int = 200) -> requests.Response:
    response = requests.Response()
    response.status_code = status
    response._content = html.encode("utf-8")
    response.headers["Content-Type"] = content_type
    # requests 가 받을 때 하는 것과 같게: charset 없는 text/* 는 ISO-8859-1 이 된다
    response.encoding = requests.utils.get_encoding_from_headers(response.headers)
    response.url = "https://www.jobkorea.co.kr/Recruit/GI_Read_Comt_Ifrm?Gno=50075934"
    return response


class CheckResponseTests(unittest.TestCase):
    def test_block_page_without_charset_stops(self):
        with self.assertRaises(BlockedByTargetSiteError):
            check_response(_response(BLOCK_PAGE, "text/html"))

    def test_block_page_with_charset_stops(self):
        with self.assertRaises(BlockedByTargetSiteError):
            check_response(_response(BLOCK_PAGE, "text/html; charset=utf-8"))

    def test_unlabeled_page_is_read_as_utf8(self):
        response = _response("<p>자격요건: 파이썬 3년 이상</p>", "text/html")
        check_response(response)
        self.assertIn("자격요건", response.text)

    def test_labeled_charset_is_kept(self):
        response = _response("<p>공고</p>", "text/html; charset=euc-kr")
        check_response(response)
        self.assertEqual(response.encoding, "euc-kr")

    def test_normal_posting_passes(self):
        check_response(_response("<p>주요업무 백엔드 API 개발</p>", "text/html; charset=utf-8"))


class DoneIdsTests(unittest.TestCase):
    """차단 페이지로 저장된 공고는 받은 것으로 치지 않아 다음 실행이 다시 받는다."""

    def _done(self, *records):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "details.jsonl"
            path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records), encoding="utf-8")
            return read_done_ids(path)

    def test_block_page_is_fetched_again(self):
        # 그날 저장된 모양 그대로: UTF-8 을 Latin-1 로 읽은 깨진 글자 + 메일 주소
        broken = "현재 보안 정책".encode("utf-8").decode("latin-1") + "\nhelpdesk@albamon.com"
        done = self._done(
            {"source_job_id": "1", "description": "자격요건 파이썬"},
            {"source_job_id": "2", "description": broken},
        )
        self.assertEqual(done, {"1"})

    def test_security_posting_is_not_a_block_page(self):
        # 수집기의 넓은 표식(「접근이 제한」)은 저장된 본문 판정에 쓰지 않는다
        done = self._done({"source_job_id": "3", "description": "주요업무: 접근이 제한된 구역의 출입 통제 시스템 운영"})
        self.assertEqual(done, {"3"})

    def test_refetched_line_counts(self):
        done = self._done(
            {"source_job_id": "2", "description": "접속이 일시적으로 제한되었습니다"},
            {"source_job_id": "2", "description": "주요업무 데이터 분석"},
        )
        self.assertEqual(done, {"2"})


class ValidateTests(unittest.TestCase):
    """적재는 차단 안내 페이지를 공고로 넣지 않는다."""

    def test_block_page_is_dropped_and_earlier_line_survives(self):
        records = [
            {"source_job_id": "7", "description": "자격요건 SQL 능숙"},
            {"source_job_id": "7", "description": "ë³´ì\nhelpdesk@albamon.com"},
            {"source_job_id": "8", "description": "접속이 일시적으로 제한되었습니다"},
        ]
        kept, stats = validate(records)
        self.assertEqual([r["description"] for r in kept], ["자격요건 SQL 능숙"])
        self.assertEqual(stats["차단 안내 페이지"], 2)


if __name__ == "__main__":
    unittest.main()
