"""본문에 낀 HTML 주석이 단어를 쪼개지 않는가.

사람인은 공고 본문에 들어온 `script` 라는 글자를 XSS 방지로 주석을 끼워 끊어 둔다.
실제 공고(SARAMIN-54892650)의 원본 HTML이 이렇다.

    <p>ㆍ주요 개발 언어 : ja<!--x-->vasc<!--x-->ript, Typesc<!--x-->ript, <br>jQuery</p>

주석이 글자 조각을 가르기 때문에 줄바꿈 구분자가 그 자리마다 줄을 나눠 본문이
`ja` / `vasc` / `ript,` 세 줄로 저장됐다. 화면이 깨지는 것보다 나쁜 것은 기술 이름이
사라지는 것이다. `JavaScript`를 못 뽑으면 사전 순위의 기술 겹침에서 통째로 빠지고,
LLM도 본문에서 그 단어를 못 본다.

저장소에서 이 모양으로 끊긴 모집 중 공고가 640건 있었다.
"""

from __future__ import annotations

import unittest

from job_matching_bot.crawling.crawl_detail import parse_detail
from job_matching_bot.ingestion.requirement_sections import split_sections
from job_matching_bot.ingestion.skill_extractor import extract_skills

URL = "https://www.saramin.co.kr/zf_user/jobs/view?rec_idx=54892650"

# 실제 공고의 그 부분을 그대로 줄인 것.
SPLIT_HTML = """
<html><body>
  <div class="jv_cont">
    <h1>프론트엔드 개발자</h1>
    <dl><dt>경력</dt><dd>신입</dd></dl>
  </div>
  <div class="jv_cont">
    <h2>상세요강</h2>
    <div>
      <p>ㆍ주요 개발 언어 : ja<!--x-->vasc<!--x-->ript, Typesc<!--x-->ript, <br>jQuery</p>
      <p>ㆍ주요 프레임워크 : React, AngularJS,<br>Node.js</p>
      <p>ㆍja<!--x-->vasc<!--x-->ript 기반 데이터 시각화</p>
    </div>
  </div>
</body></html>
"""


class CommentSplitTest(unittest.TestCase):
    def setUp(self):
        self.body = parse_detail(SPLIT_HTML, "54892650", URL)["description"]

    def test_the_word_is_whole_again(self):
        self.assertIn("javascript, Typescript,", self.body)
        self.assertNotIn("vasc", self.body.replace("javascript", ""))

    def test_the_skill_names_are_found(self):
        """이게 진짜 손해였다. 쪼개진 글자에서는 기술을 뽑을 수 없다."""
        found = extract_skills(self.body)
        for name in ("JavaScript", "TypeScript", "jQuery", "React"):
            self.assertIn(name, found, f"{name} 이(가) 안 잡혔다")

    def test_real_line_breaks_are_kept(self):
        """`<br>`과 `<p>`는 진짜 줄바꿈이다. 주석만 지우고 이건 그대로 둔다."""
        lines = self.body.splitlines()
        self.assertIn("jQuery", lines)
        self.assertIn("Node.js", lines)

    def test_a_body_without_comments_is_untouched(self):
        plain = SPLIT_HTML.replace("<!--x-->", "")
        self.assertEqual(self.body, parse_detail(plain, "1", URL)["description"])

    def test_the_comment_content_never_leaks_into_the_body(self):
        html = SPLIT_HTML.replace("<!--x-->", "<!-- 관리자 메모: 이 공고는 대행 -->")
        self.assertNotIn("관리자 메모", parse_detail(html, "1", URL)["description"])


# 같은 장치인데 글자 조각이 서로 다른 `<span>` 안에 들어간 모양. 실제 공고
# SARAMIN-54871593 이 이렇다. 주석만 지워서는 안 붙는다.
SPAN_HTML = """
<html><body>
  <div class="jv_cont"><h1>웹 개발자</h1><dl><dt>경력</dt><dd>신입</dd></dl></div>
  <div class="jv_cont">
    <h2>상세요강</h2>
    <p><span>PHP(Laravel), ja</span><!--x--><span>vasc</span><!--x--><span>ript(Vue.js), SQL</span></p>
    <p>ㆍ<b>경력</b> : 신입</p>
  </div>
</body></html>
"""


class SpanSplitTest(unittest.TestCase):
    """조각이 태그 경계를 넘어 갈라진 경우.

    `smooth()`는 같은 부모 안의 이웃한 글자만 합친다. 서로 다른 `<span>` 안에 있으면
    주석을 지워도 그대로 갈라져 있다. 줄을 나누지 않는 인라인 태그를 벗겨야 붙는다.
    """

    def setUp(self):
        self.body = parse_detail(SPAN_HTML, "1", URL)["description"]

    def test_the_word_crosses_the_tag_boundary(self):
        self.assertIn("PHP(Laravel), javascript(Vue.js), SQL", self.body)

    def test_the_skill_names_are_found(self):
        found = extract_skills(self.body)
        for name in ("JavaScript", "PHP", "SQL", "Vue.js"):
            self.assertIn(name, found, f"{name} 이(가) 안 잡혔다")

    def test_an_inline_tag_does_not_split_a_line(self):
        """`ㆍ<b>경력</b> : 신입` 이 세 줄이 되면 안 된다."""
        self.assertIn("ㆍ경력 : 신입", self.body)

    def test_block_tags_still_break_lines(self):
        """인라인만 벗긴다. `<p>`가 내는 줄바꿈은 그대로다."""
        lines = self.body.splitlines()
        self.assertIn("PHP(Laravel), javascript(Vue.js), SQL", lines)
        self.assertIn("ㆍ경력 : 신입", lines)


# 같은 공고의 표 부분. 머리글 행과 내용 행이 따로 있다.
TABLE_HTML = """
<html><body>
  <div class="jv_cont"><h1>프론트엔드 개발자</h1><dl><dt>경력</dt><dd>신입</dd></dl></div>
  <div class="jv_cont">
    <h2>상세요강</h2>
    <table>
      <tr><th>근무부서</th><th>담당업무</th><th>자격요건</th><th>우대사항</th></tr>
      <tr>
        <td>웹 프론트엔드</td>
        <td><p>ㆍ웹 프론트엔드 개발</p></td>
        <td><p>ㆍ개발에 대한 기본지식 보유자</p><p>ㆍ언어 개발 능숙한자</p></td>
        <td><p>ㆍWordpress 경험자</p><p>ㆍ대졸 이상</p></td>
      </tr>
    </table>
  </div>
</body></html>
"""


class HeaderTableTest(unittest.TestCase):
    """머리글 행이 따로 있는 표를 `머리글 → 그 칸 내용` 순서로 펴는가.

    안 펴면 머리글 넷이 먼저 붙어 나오고 내용이 뒤에 몰린다. `자격요건` 다음 줄이
    곧바로 `우대사항`이 되어 자격요건이 빈 것으로 읽히고 본문 전체가 우대사항으로
    들어간다. 하드 필터가 거는 요구 전공·자격증·연차는 자격요건 구간에서만 뽑으므로,
    그 구간이 비면 그 공고는 아무 조건도 안 건 채 지나간다.
    """

    def setUp(self):
        self.body = parse_detail(TABLE_HTML, "1", URL)["description"]

    def test_each_heading_sits_above_its_own_content(self):
        self.assertIn("자격요건\nㆍ개발에 대한 기본지식 보유자", self.body)
        self.assertIn("우대사항\nㆍWordpress 경험자", self.body)

    def test_the_headings_no_longer_run_together(self):
        self.assertNotIn("자격요건\n우대사항", self.body)

    def test_the_sections_split_the_way_the_hard_filter_reads_them(self):
        sections = split_sections(self.body)
        self.assertIn("ㆍ개발에 대한 기본지식 보유자", sections.required)
        self.assertIn("ㆍWordpress 경험자", sections.preferred)
        self.assertNotIn("ㆍ개발에 대한 기본지식 보유자", sections.preferred)

    def test_a_heading_row_in_thead_is_still_found(self):
        """머리글이 `<thead>`, 내용이 `<tbody>`면 둘은 형제가 아니다.

        `find_next_sibling`으로 찾다가 조용히 건너뛰고 있었다. 실제 공고
        SARAMIN-54681126 이 그 모양이고, 자격요건이 빈 것으로 읽혀 `경력 : 해당 분야
        5년 이상` 같은 진짜 요건이 통째로 사라졌다.
        """
        html = """
        <html><body>
          <div class="jv_cont"><h1>PM</h1><dl><dt>경력</dt><dd>경력</dd></dl></div>
          <div class="jv_cont">
            <h2>상세요강</h2>
            <table>
              <thead><tr><th>모집부문</th><th>담당업무</th><th>자격요건</th><th>근무지역</th></tr></thead>
              <tbody><tr>
                <th>데이터센터 구축</th>
                <td>ㅇ 설계·구축 총괄</td>
                <td>ㅇ 경력 : 해당 분야 5년 이상</td>
                <td>본사</td>
              </tr></tbody>
            </table>
          </div>
        </body></html>
        """
        body = parse_detail(html, "1", URL)["description"]
        self.assertIn("자격요건\nㅇ 경력 : 해당 분야 5년 이상", body)
        self.assertIn("ㅇ 경력 : 해당 분야 5년 이상", split_sections(body).required)

    def test_a_mismatched_row_is_left_alone(self):
        """rowspan 등으로 칸 수가 안 맞으면 건드리지 않는다. 잘못 붙이느니 그대로 둔다."""
        html = TABLE_HTML.replace("<td>웹 프론트엔드</td>", "")
        body = parse_detail(html, "1", URL)["description"]
        self.assertIn("근무부서", body)
        self.assertIn("ㆍWordpress 경험자", body)

    def test_a_table_without_a_heading_row_is_untouched(self):
        html = TABLE_HTML.replace("<th>", "<td>").replace("</th>", "</td>")
        body = parse_detail(html, "1", URL)["description"]
        self.assertIn("ㆍ개발에 대한 기본지식 보유자", body)


if __name__ == "__main__":
    unittest.main()
