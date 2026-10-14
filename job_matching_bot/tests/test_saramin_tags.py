"""해시태그 블록에서 기술스택을 얻는 경로 검증.

3,100건 실측: 숨김 분류 블록은 2%에만 있었고, 해시태그 블록은 표준 UI라 모든
공고에 있다. 기술스택의 실제 출처는 후자다.
"""

import tempfile
import unittest
from pathlib import Path

from job_matching_bot.config import REPO_ROOT
from job_matching_bot.ingestion.record_files import append_record, latest_by_id, read_records
from job_matching_bot.ingestion.saramin import normalize_saramin
from job_matching_bot.ingestion.saramin_tech_vocab import (
    AXIS_FIELD,
    AXIS_ROLE,
    AXIS_TECH_STACK,
    FIELD_AS_TECH,
    TOOL_AS_TECH,
    axis_of,
    is_tech_tag,
    load_codes,
    split_tags,
    tech_stack_codes,
)

from job_matching_bot.crawling.crawl_detail import done_record_ids, parse_detail

# 사람인 상세 페이지의 뼈대만 흉내 낸 HTML. 핵심 정보 dl 과 해시태그 블록.
SAMPLE_HTML = """
<html><body>
<section class="jview">
  <div class="jv_cont jv_summary"><h2>핵심 정보</h2>
    <dl><dt>경력</dt><dd>신입·경력</dd></dl>
    <dl><dt>학력</dt><dd>학력무관</dd></dl>
    <dl><dt>근무형태</dt><dd>정규직</dd></dl>
    <dl><dt>근무지역</dt><dd>경기 수원시</dd></dl>
  </div>
  <div class="jv_cont jv_detail"><h2 class="jv_title">상세요강</h2>
    <div class="cont"><div class="user_content">센서 제어 펌웨어를 개발합니다. C/C++ 경험자 우대.</div></div>
  </div>
  <div class="cont"><div class="tags">
    <a>#IT개발·데이터</a> <a>#SE(시스템엔지니어)</a> <a>#펌웨어</a> <a>#RTOS</a>
    <a>#C#</a> <a>#C++</a> <a>#PLC</a> <a>#경기</a> <a>#수원시</a> <a>#C++</a>
  </div></div>
</section>
</body></html>
"""

BASE = {
    "source_job_id": "1",
    "source_url": "https://www.saramin.co.kr/zf_user/jobs/view?rec_idx=1",
    "conditions": {"경력": "신입", "학력": "학력무관", "근무형태": "정규직", "근무지역": "경기 수원시"},
    "company_info": {},
    "description": "본문",
    "needs_human_review": False,
    "list_item": {"company": "테스트", "title": "센서 개발", "job_sectors": ["펌웨어"], "support_text": "상시채용"},
}


class ParseTagsTest(unittest.TestCase):
    def test_hashtags_are_collected_in_order_without_duplicates(self):
        record = parse_detail(SAMPLE_HTML, "1", "https://www.saramin.co.kr/zf_user/jobs/view?rec_idx=1")
        self.assertEqual(
            ["IT개발·데이터", "SE(시스템엔지니어)", "펌웨어", "RTOS", "C#", "C++", "PLC", "경기", "수원시"],
            record["tags"],
        )
        self.assertEqual("saramin-detail-poc-0.3.0", record["parser_version"])
        # 기존 필드도 그대로 나온다.
        self.assertEqual("신입·경력", record["conditions"]["경력"])


class TechVocabTest(unittest.TestCase):
    """분류는 손으로 만든 목록이 아니라 사람인 공식 코드표(fixtures/saramin_job_codes.json)를 따른다."""

    def test_code_table_is_loaded_with_it_axes(self):
        rows = load_codes()
        self.assertGreater(len(rows), 2000)
        it = [r for r in rows if r["mcls_code"] == 2]
        axes = {r["scls_name"] for r in it}
        self.assertEqual({AXIS_ROLE, AXIS_FIELD, AXIS_TECH_STACK}, axes)
        self.assertEqual(140, sum(1 for r in it if r["scls_name"] == AXIS_TECH_STACK))

    def test_axis_lookup_uses_official_table(self):
        self.assertEqual(AXIS_ROLE, axis_of("백엔드/서버개발"))
        self.assertEqual(AXIS_FIELD, axis_of("네트워크"))
        self.assertEqual(AXIS_TECH_STACK, axis_of("#Python"))
        # 지역 태그는 표에 없다.
        self.assertIsNone(axis_of("수원시"))

    def test_tech_stack_axis_is_tech_with_spelling_variants(self):
        for tag in ("Java", "#Python", "C#", "C++", "SpringBoot", "Spring Boot", "ReactJS", "Node.js",
                    "임베디드리눅스", "풀스택", "Solidity"):
            self.assertTrue(is_tech_tag(tag), tag)

    def test_allowlisted_field_and_tool_entries_are_tech(self):
        for tag in ("RTOS", "DevOps", "ERP", "SAP", "펌웨어", "딥러닝", "PLC", "Figma", "CAD"):
            self.assertTrue(is_tech_tag(tag), tag)

    def test_roles_domains_regions_and_equipment_are_not_tech(self):
        for tag in ("IT개발·데이터", "백엔드/서버개발", "SE(시스템엔지니어)", "개발PM", "경기", "수원시",
                    "신입·인턴", "영업관리", "반도체", "네트워크", "정보보안", "핀테크", "헬스케어",
                    "크레인", "용접기"):
            self.assertFalse(is_tech_tag(tag), tag)

    def test_allowlists_only_name_entries_that_exist_in_the_table(self):
        # 허용 목록에 오타가 있으면 조용히 무시되므로 여기서 잡는다.
        rows = load_codes()
        field_names = {r["kewd_name"] for r in rows if r["scls_name"] == AXIS_FIELD}
        tool_names = {r["kewd_name"] for r in rows if r["scls_name"] in ("작업Tool", "작업도구")}
        self.assertEqual(set(), FIELD_AS_TECH - field_names)
        self.assertEqual(set(), TOOL_AS_TECH - tool_names)

    def test_tech_stack_codes_map_names_to_cat_kewd(self):
        codes = tech_stack_codes()
        self.assertEqual(272, codes["Python"])
        self.assertEqual(214, codes["Docker"])
        self.assertEqual(140, len(codes))

    def test_split_keeps_order_and_collapses_variants(self):
        tech, other = split_tags(["#백엔드/서버개발", "#Java", "#ReactJS", "#React", "#서울", "#Java"])
        self.assertEqual(["Java", "ReactJS"], tech)
        self.assertEqual(["백엔드/서버개발", "서울"], other)


class NormalizeWithTagsTest(unittest.TestCase):
    def test_tags_fill_tech_stack_and_keywords(self):
        record = {**BASE, "tags": ["IT개발·데이터", "펌웨어", "RTOS", "C#", "C++", "경기"]}
        job = normalize_saramin(record)
        self.assertEqual(["펌웨어", "RTOS", "C#", "C++"], job.tech_stack)
        self.assertEqual(["IT개발·데이터", "경기"], job.keywords)
        self.assertEqual("tags", job.field_provenance["tech_stack"]["method"])
        self.assertEqual(["펌웨어", "RTOS", "C#", "C++"], job.field_provenance["tech_stack"]["from_tags"])
        # 직무 태그가 매칭 텍스트에 들어가 직무 점수의 근거가 된다.
        self.assertIn("it개발·데이터", job.matching_text())

    def test_hidden_block_and_tags_are_merged_without_duplicates(self):
        record = {
            **BASE,
            "description": "상세요강\n선택 : IT개발·데이터 > 기술스택 > Python\n선택 : IT개발·데이터 > 기술스택 > Git\n",
            "tags": ["Python", "Docker"],
        }
        job = normalize_saramin(record)
        self.assertEqual(["Python", "Git", "Docker"], job.tech_stack)
        self.assertEqual("hidden_block+tags", job.field_provenance["tech_stack"]["method"])

    def test_records_from_old_parser_without_tags_still_normalize(self):
        job = normalize_saramin(BASE)
        self.assertEqual([], job.tech_stack)
        self.assertEqual([], job.keywords)


class RefetchPlanningTest(unittest.TestCase):
    def test_latest_record_wins_when_a_job_was_fetched_twice(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "d.jsonl"
            append_record(path, {"source_job_id": "1", "description": "old"})
            append_record(path, {"source_job_id": "2", "description": "x"})
            append_record(path, {"source_job_id": "1", "description": "new", "tags": ["Java"]})
            latest = latest_by_id(read_records(path))
            self.assertEqual(2, len(latest))
            self.assertEqual("new", latest["1"]["description"])

    def test_records_missing_the_required_field_are_not_done(self):
        records = [
            {"source_job_id": "1"},                      # 예전 파서: tags 없음
            {"source_job_id": "2", "tags": []},          # 새 파서: 태그가 없어도 필드는 있음
            {"source_job_id": "3", "tags": ["Java"]},
        ]
        self.assertEqual({"1", "2", "3"}, done_record_ids(records))
        self.assertEqual({"2", "3"}, done_record_ids(records, require_field="tags"))


if __name__ == "__main__":
    unittest.main()
