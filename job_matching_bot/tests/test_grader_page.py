"""채점 페이지 — 사람이 한 화면에서 매기고 그대로 채점에 넘긴다.

원래는 `읽기.md`로 판단하고 `채점표.csv`의 같은 번호 줄에 옮겨 적는 방식이었다.
30줄을 매기려면 서른 번 오가야 해서 9월 7일에 두 번 만들어 두고 한 줄도 안 채워졌다.

여기서 지키는 것 넷.

1. **파일 하나로 열린다.** 바깥에서 받아오는 것이 있으면 인터넷 없이는 못 쓴다.
2. **공고 글이 페이지를 깨뜨리지 않는다.** 본문에 `</script>`가 들어 있어도 안전해야 한다.
3. **내려받는 CSV가 `--score`가 읽는 형식과 같다.** 어긋나면 매긴 30줄이 버려진다.
4. **양쪽 조건을 나란히 보여준다.** 공고가 대졸을 요구하는 것만 보이고 이 사람이
   대졸인지는 안 보이면, 학력·연차·지역은 매길 수가 없다.
"""

from __future__ import annotations

import json
import re
import unittest

from job_matching_bot.evaluation.grader_page import build_page
from job_matching_bot.evaluation.recommend_eval import SHEET_COLUMNS, resume_skills

ITEM = {
    "번호": 1,
    "이력서": "프론트엔드 수료생",
    "순위": 1,
    "job_id": "SARAMIN-1",
    "회사": "(주)테스트",
    "공고": "프론트엔드 개발자",
    "공고링크": "https://example.com/1",
    "모델_등급": "높음",
    "근거": [{"claim": "React 경험", "resume_quote": "React로 만들었습니다", "job_quote": "React 경험자"}],
    "우려": ["AWS 경험이 확인되지 않는다"],
    "공고_기술": "React, TypeScript",
    "자격요건": ["React 경험 2년 이상"],
    "우대사항": ["Next.js 경험"],
    "조건": "서울 강남구 · 신입 · 대졸 · 정규직",
    "공고_자격증": "정보처리기사",
    "공고_전공": "컴퓨터·소프트웨어",
    "공고_우대자격증": "SQLD",
    "공고_우대전공": "통계·수학",
    "이력서_기술": "React, TypeScript",
    "이력서_자격증": "웹디자인기능사",
    "이력서_전공": "시각디자인학과",
}
PERSONAS = {
    "프론트엔드 수료생": {
        "resume_text": "React와 TypeScript로 화면을 만들었습니다.",
        "preferred_regions": ["서울"],
        "preferred_employment_types": ["정규직"],
        "education_level": "대졸",
        "career_years": 0,
    }
}


def _payload(html: str) -> list[dict]:
    body = re.search(r'<script id="items" type="application/json">(.*?)</script>', html, re.S)
    return json.loads(body.group(1).replace("<\\/", "</"))


class GraderPageTest(unittest.TestCase):
    def test_the_page_is_self_contained(self):
        html = build_page([ITEM], PERSONAS, "20260910-000000")
        outside = re.findall(r'(?:src|href)="https?://[^"]+', html)
        self.assertEqual([], outside, "글꼴·스크립트를 바깥에서 받아오면 안 된다")
        # 공고 원문 링크는 화면을 그릴 때 만들어진다. 정적 HTML이 아니라 데이터에 있다.
        self.assertEqual("https://example.com/1", _payload(html)[0]["공고링크"])

    def test_resume_text_travels_with_the_item(self):
        """옆에 다른 파일을 열어 두지 않아도 이력서를 볼 수 있어야 한다."""
        data = _payload(build_page([ITEM], PERSONAS, "s"))
        self.assertEqual("React와 TypeScript로 화면을 만들었습니다.", data[0]["이력서_전문"])

    def test_a_script_tag_in_the_posting_does_not_break_the_page(self):
        """공고 본문은 남이 쓴 글이다. `</script>`가 들어 있으면 블록이 일찍 닫힌다."""
        nasty = {**ITEM, "자격요건": ["</script><script>alert(1)</script> 경험"]}
        html = build_page([nasty], PERSONAS, "s")
        body = re.search(r'<script id="items" type="application/json">(.*?)</script>', html, re.S)
        self.assertNotIn("</script>", body.group(1))
        self.assertIn("alert(1)", _payload(html)[0]["자격요건"][0], "내용 자체는 살아 있어야 한다")

    def test_downloaded_csv_matches_the_scoring_format(self):
        """페이지가 만드는 열 이름이 `--score`가 읽는 것과 같아야 한다."""
        html = build_page([ITEM], PERSONAS, "s")
        header = re.search(r"const head = \[([^\]]+)\]", html).group(1)
        columns = tuple(re.findall(r"'([^']+)'", header))
        self.assertEqual(SHEET_COLUMNS, columns)

    def test_progress_is_kept_per_run(self):
        """실행마다 따로 저장한다. 새 실행이 옛 채점을 덮어쓰면 안 된다."""
        a = build_page([ITEM], PERSONAS, "20260910-000000")
        b = build_page([ITEM], PERSONAS, "20260911-000000")
        self.assertIn('data-stamp="20260910-000000"', a)
        self.assertIn('data-stamp="20260911-000000"', b)

    def test_every_item_is_included(self):
        items = [{**ITEM, "번호": n} for n in range(1, 31)]
        self.assertEqual(30, len(_payload(build_page(items, PERSONAS, "s"))))


class ApplicantTermsTest(unittest.TestCase):
    """공고 쪽 `학력무관 · 경력무관`과 맞대어 볼 지원자 쪽 한 줄."""

    def test_education_and_years_are_shown(self):
        terms = _payload(build_page([ITEM], PERSONAS, "s"))[0]["이력서_조건"]
        self.assertIn("대졸", terms)
        self.assertIn("연차 0", terms)
        self.assertIn("서울", terms)
        self.assertIn("정규직", terms)

    def test_an_unstated_preference_reads_as_no_limit(self):
        """희망을 안 적은 것은 '아무 데나'다. 빈칸으로 두면 못 맞춘 것처럼 보인다."""
        bare = {"프론트엔드 수료생": {"resume_text": "", "education_level": "고졸", "career_years": 5}}
        terms = _payload(build_page([ITEM], bare, "s"))[0]["이력서_조건"]
        self.assertIn("지역 무관", terms)
        self.assertIn("형태 무관", terms)
        self.assertIn("고졸", terms)

    def test_certifications_and_majors_are_shown_on_both_sides(self):
        """공고가 정보처리기사를 요구하는데 이 사람이 뭘 가졌는지 안 보이면 못 매긴다."""
        data = _payload(build_page([ITEM], PERSONAS, "s"))[0]
        self.assertEqual("정보처리기사", data["공고_자격증"])
        self.assertEqual("웹디자인기능사", data["이력서_자격증"])
        self.assertEqual("컴퓨터·소프트웨어", data["공고_전공"])
        self.assertEqual("시각디자인학과", data["이력서_전공"])

    def test_preferred_qualifications_are_kept_apart_from_required(self):
        """우대 자격증을 필수처럼 보여주면 지원 가능한 공고를 포기하게 만든다."""
        data = _payload(build_page([ITEM], PERSONAS, "s"))[0]
        self.assertEqual("SQLD", data["공고_우대자격증"])
        self.assertEqual("통계·수학", data["공고_우대전공"])
        self.assertNotEqual(data["공고_자격증"], data["공고_우대자격증"])

    def test_a_missing_persona_does_not_crash_the_page(self):
        terms = _payload(build_page([ITEM], {}, "s"))[0]["이력서_조건"]
        self.assertIn("미기재", terms)


class ResumeSkillsTest(unittest.TestCase):
    """채점하는 사람이 옆에 놓고 볼 값. 비어 있으면 공고와 맞대어 볼 것이 없다."""

    def test_a_skill_section_wins(self):
        text = "[기술스택]\nReact\nTypeScript\n\n[경력사항]\n- 어딘가"
        self.assertEqual("React, TypeScript", resume_skills(text))

    def test_the_proficiency_suffix_is_dropped(self):
        """앱은 `Java (고급)` 처럼 적는다. 공고 기술과 나란히 볼 값이라 이름만 남긴다."""
        text = "[기술스택]\nJava (고급)\nSpring Boot (중급)"
        self.assertEqual("Java, Spring Boot", resume_skills(text))

    def test_project_skill_lines_are_gathered(self):
        text = "[프로젝트]\n- 추천 서비스\n  기술: Python, FastAPI\n- 대시보드\n  기술: Python, React"
        self.assertEqual("Python, FastAPI, React", resume_skills(text))

    def test_prose_falls_back_to_the_vocabulary(self):
        """경력 이력서는 문장 안에 기술을 적는다. 구간만 보면 기술이 없는 것처럼 보였다."""
        text = (
            "[경력사항]\n"
            "- (주)테크커머스 백엔드 개발자\n"
            "  Java, Spring Boot 기반 주문 시스템을 개발했습니다.\n"
            "  Kafka 기반 이벤트 처리를 도입했습니다."
        )
        found = resume_skills(text)
        for name in ("Java", "Spring Boot", "Kafka"):
            self.assertIn(name, found, f"{name} 이(가) 문장에서 안 잡혔다")

    def test_nothing_to_find(self):
        self.assertEqual("", resume_skills("[자기소개서]\n성실히 배우겠습니다."))


if __name__ == "__main__":
    unittest.main()
