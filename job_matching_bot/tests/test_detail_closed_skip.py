"""마감된 공고는 상세를 저장하지 않는다.

밤 배치는 시간이 한정돼 있다(실측 6시간 반에 4,200여 건). 그 시간을 마감된 공고에
쓰면 살아 있는 공고가 그만큼 뒤로 밀린다. 게다가 마감 페이지는 본문이 비어 있어
요건을 못 뽑고, 추천 후보도 되지 못한 채 저장소만 차지한다.

판정은 **이미 받아 온 페이지**로 한다. 요청도 파싱도 더 들지 않는다.
"""

from __future__ import annotations

import unittest

from job_matching_bot.crawling.crawl_detail import is_closed_page, parse_detail

URL = "https://www.saramin.co.kr/zf_user/jobs/view?rec_idx=1"

# 마감 문구는 태그로 끊겨 있다. 원본 문자열에서 찾으면 안 걸린다.
CLOSED_HTML = """
<html><body>
  <div class="jv_cont">
    <h1>프론트엔드 개발자</h1>
    <dl><dt>경력</dt><dd>신입</dd></dl>
  </div>
  <div class="jv_cont">
    <h2>상세요강</h2>
    <p>본 채용정보는 <strong>마감</strong>되었습니다.</p>
  </div>
</body></html>
"""

OPEN_HTML = """
<html><body>
  <div class="jv_cont">
    <h1>프론트엔드 개발자</h1>
    <dl><dt>경력</dt><dd>신입</dd></dl>
  </div>
  <div class="jv_cont">
    <h2>상세요강</h2>
    <p>자격요건: React와 TypeScript로 화면을 만들어 본 분을 찾습니다.</p>
  </div>
</body></html>
"""

GONE_HTML = "<html><body><p>삭제된 공고입니다.</p></body></html>"


class ClosedDetectionTest(unittest.TestCase):
    def test_a_closed_posting_is_marked(self):
        self.assertTrue(parse_detail(CLOSED_HTML, "1", URL)["closed"])

    def test_an_open_posting_is_not(self):
        self.assertFalse(parse_detail(OPEN_HTML, "1", URL)["closed"])

    def test_a_deleted_page_counts_as_closed(self):
        self.assertTrue(parse_detail(GONE_HTML, "1", URL)["closed"])

    def test_the_marker_is_read_from_text_not_raw_html(self):
        # `채용정보는 <strong>마감</strong>되었습니다` — 원본에는 이어진 글자가 없다.
        self.assertNotIn("채용정보는 마감", CLOSED_HTML)
        self.assertTrue(is_closed_page(CLOSED_HTML))

    def test_a_page_without_the_posting_body_counts_as_closed(self):
        # `.jv_cont`가 하나도 없으면 공고 페이지가 아니다. 오류 페이지일 수도 있다.
        self.assertTrue(is_closed_page("<html><body><p>안내</p></body></html>"))


if __name__ == "__main__":
    unittest.main()
