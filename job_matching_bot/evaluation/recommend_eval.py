"""추천 판단을 사람이 매긴 정답과 대조한다.

    python -m job_matching_bot.evaluation.recommend_eval --run     # 추천을 받아 채점표를 만든다
    python -m job_matching_bot.evaluation.recommend_eval --score   # 채운 채점표로 점수를 낸다

## 왜 필요한가

지금까지는 결과를 눈으로 보고 "괜찮아 보인다"고 판단했다. 그래서 응답 속도를 올렸을 때
적합도가 후해진 것을 한참 뒤에야 분포를 비교하다 알아챘다(높음 14 → 17 → 20). 사람이
한 번 정답을 매겨 두면, 그다음부터 어떤 변경이든 숫자로 비교할 수 있다.

## 쓰는 법

1. `--run` 으로 이력서 6종의 추천을 받는다. `<시각>-채점.html` 을 브라우저로 연다.
2. 공고 요건과 이력서가 나란히 나온다. 키 하나로 매기고 다음으로 넘어간다.
   - `1` 추천·높음 (직무가 같고 주된 기술이 겹친다)
   - `2` 추천·보통 (직무는 같은데 주된 기술이 다르다)
   - `3` 추천 안 함
   모델의 등급과 근거는 **접혀** 있다. 먼저 스스로 정한 뒤 펼친다.
   중간에 꺼도 된다 — 매긴 값은 브라우저에 남고 실행마다 따로 저장된다.
3. 30건을 다 매기면 내려받기 단추가 나온다. 받은 파일을 `fixtures/eval_labels.csv` 로
   옮기고 `--score` 를 돌린다.
4. 이후 프롬프트·모델·추론 강도를 바꿀 때마다 `--run` 후 `--score` 로 비교한다.

엑셀로 채우고 싶으면 함께 만들어지는 `<시각>-채점표.csv` 와 `<시각>-읽기.md` 를 쓴다.
번호로 이어지는 예전 방식이다.

정답은 사람이 매긴다. 모델이 낸 등급을 정답으로 쓰면 자기 답안을 자기가 채점하는 셈이라
아무것도 검증하지 못한다.
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import re
import sys
import time
import urllib.error
import urllib.request
from collections import Counter
from pathlib import Path

from job_matching_bot.config import ARTIFACTS_DIR, FIXTURES_DIR
from job_matching_bot.evaluation.grader_page import write_page
from job_matching_bot.evaluation.app_resume import EVAL_MOCKS, MOCKS, load_personas
from job_matching_bot.ingestion.skill_extractor import extract_skills

DEFAULT_BASE_URL = "http://127.0.0.1:8000"
# 이력서 원본은 앱과 같은 `scripts/resume_mocks.json` 하나다. 여기서 따로 갖지 않는다.
LABELS = FIXTURES_DIR / "eval_labels.csv"

# 어느 이력서 벌로 잴지. `--eval-resumes`가 바꾼다.
#
# 기본은 앱 목업 5종이다. `--eval-resumes`를 주면 평가 전용 5종을 쓴다. 프롬프트나
# 가중치를 그 5종을 보고 고쳤다면 같은 것으로 다시 재면 안 된다 — 자기 데이터에 맞춘
# 셈이라 항상 좋아 보인다.
_RESUME_SET = {"path": MOCKS}
RUNS_DIR = ARTIFACTS_DIR / "eval"

# 채점표에서 사람이 채우는 칸. 비어 있으면 아직 라벨이 없는 줄이다.
LABEL_COLUMNS = ("사람_추천여부", "사람_등급", "메모")
# 채우는 표는 짧게 둔다. 자격요건 500자를 엑셀 셀에 넣으면 아무도 못 읽는다.
# 판단에 필요한 긴 내용은 옆에 두고 읽을 문서(.md)에 따로 쓴다. 번호로 이어진다.
SHEET_COLUMNS = ("번호", "이력서", "회사", "공고", *LABEL_COLUMNS)
# 문서에 넣을 자격요건·우대사항 줄 수 상한.
MAX_REQUIREMENT_LINES = 12


def resume_skills(resume_text: str) -> str:
    """이력서 평문에서 기술만 뽑는다. 공고 기술과 나란히 놓고 보기 위한 것.

    `[기술스택]` 구간이 있으면 그것을 쓰고, 없으면 프로젝트·교육의 `기술:` 줄을 모은다.
    앱 이력서는 기술스택 항목이 따로 있지만, 평가용 이력서는 프로젝트 안에 적혀 있다.

    둘 다 없으면 어휘 사전으로 본문에서 훑는다. 경력 이력서는 "Java, Spring Boot 기반
    주문 시스템을 개발했습니다"처럼 문장 안에 기술을 적어서, 구간만 보면 기술이
    하나도 없는 것처럼 보였다. 채점하는 사람이 옆에 놓고 볼 값이라 비어 있으면 곤란하다.
    추천에는 쓰이지 않는다 — 그쪽은 LLM이 뽑은 `profile.skills` 를 쓴다.
    """
    stack: list[str] = []
    listed: list[str] = []
    inside = False
    for line in resume_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            inside = stripped == "[기술스택]"
            continue
        if inside and stripped:
            # 앱은 `Java (고급)` 처럼 숙련도를 괄호로 붙인다. 공고 기술과 나란히 볼
            # 값이라 이름만 남긴다.
            stack.append(re.sub(r"\s*\(.*\)$", "", stripped).strip())
        elif stripped.startswith("기술:"):
            listed.append(stripped[len("기술:"):].strip())

    if stack:
        return ", ".join(stack)
    # 여러 프로젝트에 같은 기술이 나오면 한 번만 둔다.
    names: list[str] = []
    for line in listed:
        for name in line.split(","):
            name = name.strip()
            if name and name not in names:
                names.append(name)
    if names:
        return ", ".join(names)
    return ", ".join(extract_skills(resume_text))


def unescape(text: str) -> str:
    """크롤 원문에 남은 HTML 엔티티를 사람이 읽는 글자로. 예: `&amp;` → `&`."""
    return html.unescape(text or "")


def job_details(job_ids: set[str]) -> dict[str, dict[str, str]]:
    """저장소에서 공고의 자격요건·우대사항·기술을 읽는다. 앱 응답에는 발췌만 있다."""
    from job_matching_bot.ingest import DEFAULT_STORE
    from job_matching_bot.ingestion.job_store import open_store
    from job_matching_bot.ingestion.requirement_sections import split_sections

    store = open_store(DEFAULT_STORE).load()
    try:
        details: dict[str, dict[str, str]] = {}
        for job_id in job_ids:
            record = store.get(job_id) if hasattr(store, "get") else None
            if record is None:
                continue
            job = record.job
            sections = split_sections(job.description)
            skills = list(dict.fromkeys([*job.required_skills, *job.preferred_skills, *job.tech_stack]))
            details[job_id] = {
                "공고_기술": ", ".join(skills),
                "자격요건": sections.required[:MAX_REQUIREMENT_LINES],
                "우대사항": sections.preferred[:MAX_REQUIREMENT_LINES],
                "공고_자격증": ", ".join(job.required_certifications),
                "공고_전공": ", ".join(job.required_majors),
                "공고_우대자격증": ", ".join(job.preferred_certifications),
                "공고_우대전공": ", ".join(job.preferred_majors),
            }
        return details
    finally:
        if hasattr(store, "close"):
            store.close()


def recommend(base_url: str, persona: dict, top_k: int = 5, timeout: int = 180) -> dict:
    body = json.dumps({**{k: v for k, v in persona.items()}, "top_k": top_k}, ensure_ascii=False)
    request = urllib.request.Request(
        f"{base_url}/api/v1/jobs/recommend",
        data=body.encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def run(base_url: str, top_k: int) -> Path:
    personas = load_personas(_RESUME_SET["path"])
    rows: list[dict] = []
    raw: dict[str, dict] = {}
    started = time.time()

    for name, persona in personas.items():
        began = time.time()
        try:
            result = recommend(base_url, persona, top_k)
        except urllib.error.URLError as error:
            print(f"  {name}: 서버 호출 실패 — {error}. 서버가 떠 있는지 확인하세요.")
            return Path()
        elapsed = time.time() - began
        raw[name] = result
        print(f"  {name:16s} {elapsed:5.1f}초 · {len(result['recommendations'])}건")
    stamp = time.strftime("%Y%m%d-%H%M%S")
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    raw_path = RUNS_DIR / f"{stamp}.json"
    raw_path.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
    items = build_items(raw, personas)
    sheet = RUNS_DIR / f"{stamp}-채점표.csv"
    _write_sheet(sheet, sheet_rows(items))
    doc = RUNS_DIR / f"{stamp}-읽기.md"
    _write_review_doc(doc, items, personas)
    rows = items
    print(f"\n{len(rows)}건 · {time.time() - started:.0f}초")
    print(f"결과 원본: {raw_path}")
    page = write_page(raw_path.with_name(raw_path.stem + "-채점.html"), items, personas)
    print(f"채점 페이지: {page}   ← 열어서 여기서 매기면 끝난다")
    print(f"읽기 문서:  {doc}   (페이지 대신 문서로 보고 싶을 때)")
    print(f"빈 채점표:  {sheet}   (엑셀로 채우고 싶을 때)")
    if not LABELS.exists():
        print(f"\n채점표를 엑셀로 열어 {LABEL_COLUMNS[0]}·{LABEL_COLUMNS[1]} 칸을 채운 뒤")
        print(f"{LABELS} 로 저장하세요. 그다음 --score 로 점수를 냅니다.")
    return raw_path


def build_items(raw: dict, personas: dict) -> list[dict]:
    """결과 원본 + 저장소 + 이력서를 합쳐 항목 하나씩 만든다. LLM을 다시 부르지 않는다.

    표와 문서가 같은 목록을 쓰고 `번호`로 이어진다.
    """
    ids = {item["job_id"] for result in raw.values() for item in result["recommendations"]}
    details = job_details(ids)
    items: list[dict] = []
    number = 0
    for name, result in raw.items():
        persona = personas.get(name, {})
        for rank, item in enumerate(result["recommendations"], 1):
            number += 1
            conditions = item.get("conditions") or {}
            detail = details.get(item["job_id"], {})
            items.append(
                {
                    "번호": number,
                    "이력서": name,
                    "순위": rank,
                    "job_id": item["job_id"],
                    "회사": unescape(item["company"]),
                    "공고": unescape(item["title"]),
                    "공고링크": item.get("source_url", ""),
                    "모델_등급": item["fit"],
                    "근거": item.get("reasons") or [],
                    "우려": item.get("concerns") or [],
                    "공고_기술": detail.get("공고_기술", ""),
                    "자격요건": detail.get("자격요건", []),
                    "우대사항": detail.get("우대사항", []),
                    "조건": " · ".join(
                        str(conditions.get(key) or "")
                        for key in ("region", "career", "education", "employment_type")
                    ),
                    "공고_자격증": detail.get("공고_자격증", ""),
                    "공고_전공": detail.get("공고_전공", ""),
                    "공고_우대자격증": detail.get("공고_우대자격증", ""),
                    "공고_우대전공": detail.get("공고_우대전공", ""),
                    "이력서_기술": resume_skills(persona.get("resume_text", "")),
                    "이력서_자격증": ", ".join(persona.get("certifications") or []),
                    "이력서_전공": ", ".join(persona.get("majors") or []),
                }
            )
    return items


def sheet_rows(items: list[dict]) -> list[dict]:
    """엑셀로 채울 짧은 표."""
    return [
        {
            "번호": item["번호"],
            "이력서": item["이력서"],
            "회사": item["회사"],
            "공고": item["공고"][:40],
            **dict.fromkeys(LABEL_COLUMNS, ""),
        }
        for item in items
    ]


def _write_review_doc(path: Path, items: list[dict], personas: dict) -> None:
    """옆에 두고 읽을 문서. 표에는 번호만 적고 판단은 여기서 한다.

    모델의 등급과 근거는 **맨 아래**에 둔다. 먼저 보면 그대로 따라가게 된다.
    """
    out: list[str] = [
        "# 추천 채점 — 읽고 판단하는 문서\n\n",
        "각 항목의 **공고가 요구하는 것**과 **이력서에 있는 것**을 비교하고, ",
        "`채점표.csv` 의 같은 번호 줄에 적으세요.\n\n",
        "- `사람_추천여부` — 이 사람에게 추천할 만한가: **예 / 아니오**\n",
        "- `사람_등급` — 예일 때만: **높음**(직무가 같고 주된 기술이 겹친다) / **보통**(직무는 같은데 주된 기술이 다르다)\n\n",
        "모델의 판단은 각 항목 맨 아래에 접어 두었습니다. **먼저 스스로 정한 뒤** 펼쳐 보세요.\n\n",
        "---\n\n",
    ]

    current = None
    for item in items:
        if item["이력서"] != current:
            current = item["이력서"]
            persona = personas.get(current, {})
            out.append(f"# 이력서 · {current}\n\n")
            out.append(f"**기술** {resume_skills(persona.get('resume_text', '')) or '(없음)'}\n\n")
            out.append(
                f"**희망** {', '.join(persona.get('preferred_regions') or []) or '지역 무관'}"
                f" · {', '.join(persona.get('preferred_employment_types') or []) or '형태 무관'}"
                f" · {persona.get('education_level', '미기재')}"
                f" · 연차 {persona.get('career_years', 0)}\n\n"
            )
            out.append("<details><summary>이력서 전문</summary>\n\n```\n")
            out.append(persona.get("resume_text", "").strip())
            out.append("\n```\n\n</details>\n\n")

        out.append(f"## {item['번호']}. {item['회사']} — {item['공고']}\n\n")
        out.append(f"`{item['조건']}`\n\n")
        if item["공고_기술"]:
            out.append(f"**공고가 고른 기술** {item['공고_기술']}\n\n")
        out.append("**자격요건**\n\n")
        out.append(_bullets(item["자격요건"], "(공고에 자격요건 구간이 없습니다)"))
        if item["우대사항"]:
            out.append("\n**우대사항**\n\n")
            out.append(_bullets(item["우대사항"], ""))
        out.append(f"\n**이력서 기술** {item['이력서_기술'] or '(없음)'}\n\n")
        if item["공고링크"]:
            out.append(f"[공고 원문 열기]({item['공고링크']})\n\n")

        out.append(f"<details><summary>모델의 판단 보기 (등급 {item['모델_등급']})</summary>\n\n")
        for reason in item["근거"]:
            out.append(f"- {reason.get('claim', '')}\n")
            out.append(f"  - 이력서: \"{reason.get('resume_quote', '')}\"\n")
            out.append(f"  - 공고: \"{reason.get('job_quote', '')}\"\n")
        if not item["근거"]:
            out.append("- (근거 없음)\n")
        if item["우려"]:
            out.append("\n확인되지 않은 요건:\n")
            for concern in item["우려"]:
                out.append(f"- {concern}\n")
        out.append("\n</details>\n\n---\n\n")

    path.write_text("".join(out), encoding="utf-8")


def _bullets(lines: list[str], empty: str) -> str:
    if not lines:
        return f"{empty}\n" if empty else ""
    return "".join(f"- {line}\n" for line in lines)


def _write_resume_sheet(path: Path, personas: dict) -> None:
    """채점하며 옆에 두고 볼 이력서 전문."""
    parts = ["# 평가용 이력서 6종\n\n"]
    for name, persona in personas.items():
        regions = ", ".join(persona.get("preferred_regions") or []) or "없음"
        types = ", ".join(persona.get("preferred_employment_types") or []) or "없음"
        parts.append(f"## {name}\n\n")
        parts.append(f"- 희망 지역: {regions}\n")
        parts.append(f"- 희망 고용형태: {types}\n")
        parts.append(f"- 학력: {persona.get('education_level', '미기재')} / 연차: {persona.get('career_years', 0)}\n\n")
        parts.append("```\n" + persona.get("resume_text", "").strip() + "\n```\n\n")
    path.write_text("".join(parts), encoding="utf-8")


def _write_sheet(path: Path, rows: list[dict]) -> None:
    # utf-8-sig: 엑셀이 한글을 깨뜨리지 않게 BOM을 붙인다.
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(SHEET_COLUMNS))
        writer.writeheader()
        writer.writerows(rows)


def load_labels(path: Path) -> dict[int, dict[str, str]]:
    """번호 → 사람이 매긴 값. 비어 있는 줄은 뺀다."""
    with path.open(encoding="utf-8-sig", newline="") as handle:
        labels: dict[int, dict[str, str]] = {}
        for row in csv.DictReader(handle):
            verdict = (row.get("사람_추천여부") or "").strip()
            if not verdict:
                continue
            try:
                number = int(str(row.get("번호", "")).strip())
            except ValueError:
                continue
            labels[number] = {
                "추천여부": verdict,
                "등급": (row.get("사람_등급") or "").strip(),
                "메모": (row.get("메모") or "").strip(),
            }
        return labels


def score(run_path: Path, labels_path: Path) -> int:
    if not labels_path.exists():
        print(f"채점표가 없습니다: {labels_path}")
        return 1
    labels = load_labels(labels_path)
    if not labels:
        print("채점표에 채워진 줄이 없습니다. 사람_추천여부 칸을 채워 주세요.")
        return 1

    raw = json.loads(run_path.read_text(encoding="utf-8"))
    personas = load_personas(_RESUME_SET["path"])
    items = build_items(raw, personas)
    checked = wrong = grade_hit = grade_total = 0
    unlabeled = 0
    model_grades: Counter = Counter()
    human_grades: Counter = Counter()
    wrong_rows: list[str] = []

    for item in items:
        model_grades[item["모델_등급"]] += 1
        label = labels.get(item["번호"])
        if label is None:
            unlabeled += 1
            continue
        checked += 1
        if label["추천여부"] not in ("예", "y", "Y"):
            wrong += 1
            wrong_rows.append(
                f"    {item['번호']:>3}. {item['이력서']} · {item['회사']} "
                f"{item['공고'][:26]} (모델 {item['모델_등급']})"
            )
            continue
        if label["등급"]:
            human_grades[label["등급"]] += 1
            grade_total += 1
            if label["등급"] == item["모델_등급"]:
                grade_hit += 1

    print(f"채점 대상 {checked}건 (라벨 없는 줄 {unlabeled}건은 건너뜀)")
    print()
    print(f"  오추천율        {wrong / checked * 100:5.1f}%  ({wrong}/{checked})  ← 낮을수록 좋다")
    if grade_total:
        print(f"  등급 일치율     {grade_hit / grade_total * 100:5.1f}%  ({grade_hit}/{grade_total})")
    print(f"  모델 등급 분포  {dict(model_grades)}")
    if human_grades:
        print(f"  사람 등급 분포  {dict(human_grades)}")
    if wrong_rows:
        print("\n  사람이 아니라고 본 추천:")
        print("\n".join(wrong_rows))
    return 0


def latest_run() -> Path | None:
    runs = sorted(RUNS_DIR.glob("*.json"))
    return runs[-1] if runs else None


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="추천 판단 평가")
    parser.add_argument("--run", action="store_true", help="추천을 받아 채점표를 만든다")
    parser.add_argument("--sheet", action="store_true", help="이미 받은 결과로 채점표만 다시 만든다(LLM 호출 없음)")
    parser.add_argument("--score", action="store_true", help="채운 채점표로 점수를 낸다")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--labels", type=Path, default=LABELS)
    parser.add_argument("--run-file", type=Path, default=None, help="채점할 결과 원본. 기본은 가장 최근 것")
    parser.add_argument(
        "--eval-resumes", action="store_true",
        help="앱 목업 대신 평가 전용 이력서 5종을 쓴다. 프롬프트를 목업으로 고쳤을 때 쓴다",
    )
    args = parser.parse_args()
    if args.eval_resumes:
        _RESUME_SET["path"] = EVAL_MOCKS
        print("평가 전용 이력서 5종을 씁니다 (앱 목업 아님)")

    if args.run:
        path = run(args.base_url, args.top_k)
        if not path.name:
            return 1
        if args.score:
            print()
            return score(path, args.labels)
        return 0

    if args.sheet:
        path = args.run_file or latest_run()
        if path is None:
            print("결과가 없습니다. 먼저 --run 을 실행하세요.")
            return 1
        personas = load_personas(_RESUME_SET["path"])
        raw = json.loads(path.read_text(encoding="utf-8"))
        items = build_items(raw, personas)
        sheet = path.with_name(path.stem + "-채점표.csv")
        _write_sheet(sheet, sheet_rows(items))
        doc = path.with_name(path.stem + "-읽기.md")
        _write_review_doc(doc, items, personas)
        page = write_page(path.with_name(path.stem + "-채점.html"), items, personas)
        print(f"채점 페이지: {page}   ← 열어서 여기서 매기면 끝난다")
        print(f"읽기 문서:  {doc}")
        print(f"빈 채점표:  {sheet}")
        return 0

    if args.score:
        path = args.run_file or latest_run()
        if path is None:
            print("채점할 결과가 없습니다. 먼저 --run 을 실행하세요.")
            return 1
        print(f"결과 원본: {path}\n")
        return score(path, args.labels)

    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
