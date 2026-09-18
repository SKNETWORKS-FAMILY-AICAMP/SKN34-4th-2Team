"""챗봇을 잰다. 정답이 있는 것은 자동으로, 답 문장은 사람이.

## 추천 평가와 다른 점

추천은 "이 공고가 이 사람에게 맞나"라 정답이 없다. 그래서 사람이 43건, 50건을 손으로
매겼다. 챗봇은 다르다. **대부분의 지표에 정답이 있다.**

    "서울 백엔드 신입 찾아줘"  →  intent 검색 · roles 백엔드 · regions 서울 · career 신입
    (목록을 보여 준 뒤) "2번"  →  job_refs [2] · 그 자리의 job_id
    "연봉 높은 순으로"          →  unavailable 급여

이건 사람이 매길 일이 아니라 대조할 일이다. 사람에게 100줄을 매기게 하면 시간만
쓰고, 정작 사람만 판단할 수 있는 것(답이 실제 공고 근거로 쓰였나, 없는 것을
지어냈나)에는 힘이 안 남는다.

그래서 셋으로 나눈다.

1. `--router` 말을 가른 결과를 대조한다. 서버가 필요 없다.
2. `--run`   앱이 보는 응답을 대조한다. 서버를 띄워 놓고 부른다.
3. `--sheet` 답 문장만 사람이 매길 페이지를 만들고, `--score` 가 그 결과를 읽는다.
   매긴 파일은 `fixtures/labels/chat-<실행시각>.csv` 로 둔다. 회차마다 한 파일이고
   지우지 않는다 — 고치기 전 숫자가 남아 있어야 좋아졌다고 말할 수 있다.

## 왜 라우터를 따로 재는가

`/api/v1/jobs/chat` 응답에는 `mode`, `filters`, `jobs`, `reply`만 있다. 앱이 쓰는
것만 담기 때문이다. **말을 가른 결과는 밖으로 나오지 않는다** — `intent`,
`counts_jobs`, `job_refs`, `unavailable`이 그렇다.

처음에는 이걸 모르고 케이스에 `intent`, `counts_jobs`를 적어 두었다. `check`가
모르는 칸은 건너뛰므로 **적어 두고도 안 본 채 전부 통과로 셌다.** 재는 줄 알았던
것을 안 재고 있었다.

그래서 라우터(`ChatService.generator`)를 직접 부르는 층을 따로 두었다. 응답에 안
실리는 칸은 여기서 본다. 서버에 재는 용도의 필드를 더하지 않으려는 것이다 — 앱이
안 쓰는 것을 API에 얹으면 그 뒤로 계속 지고 가야 한다.

같은 프롬프트·같은 입력이지만 **서버가 실제로 쓴 그 호출은 아니다.** 모델이 늘 같은
답을 주지 않으므로, 여기서 맞았다고 서버 호출도 맞았다는 보장은 없다. 갈래가 흔들리는
말을 찾는 용도로 본다.

## 여러 턴

서버는 대화를 저장하지 않는다. 앞 턴의 응답에서 `filters`와 `jobs`를 꺼내 다음 턴에
그대로 실어 보낸다. 앱이 하는 것과 같다. 그래야 "서울만", "2번 자세히"가 이어진다.
라우터만 잴 때는 앞 턴이 뽑은 `filters`를 그대로 잇는다.

## 실행

    python -m job_matching_bot.evaluation.chat_eval --router
    python -m job_matching_bot.evaluation.chat_eval --run
    python -m job_matching_bot.evaluation.chat_eval --sheet
    python -m job_matching_bot.evaluation.chat_eval --score
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from collections import Counter
from typing import Any

from job_matching_bot.config import ARTIFACTS_DIR, FIXTURES_DIR

CASES = FIXTURES_DIR / "chat_cases.json"
RUNS_DIR = ARTIFACTS_DIR / "chat_eval"
DEFAULT_BASE_URL = "http://127.0.0.1:8000"

# ── 답 규율 ───────────────────────────────────────────────────
#
# 정답은 없지만 **사람 없이도 확실히 틀렸다고 말할 수 있는 것**들이다. 답이 좋은지는
# 여기서 묻지 않는다 — 그건 취향이 섞이고, 취향을 결함으로 세면 숫자가 뜻을 잃는다.
# 그건 채점 페이지에서 사람이 매긴다.

OFF_TOPIC_MARK = "채용과 취업 준비에 대해서만"
GUIDE_MARK = "공고를 찾으시려면"
# 존댓말 종결. 하나도 없으면 반말로 답한 것으로 본다. 낱말 하나로 가르면 오판이 많다.
_POLITE = re.compile(r"(요|다|까|죠)[.!?]|(요|다|까|죠)$", re.MULTILINE)
_AB_LABEL = re.compile(r"(?<![A-Za-z])[AB](?=[는은이가의와과])")
_MD_TABLE = re.compile(r"\|\s*-{2,}")
_COUNT = re.compile(r"([\d,]+)\s*건")


def rule_말투(got: dict) -> str | None:
    """존댓말 종결이 하나도 없으면 반말로 답한 것이다.

    사용자가 반말로 물으면 모델이 따라갔다. "알아. ... 줄여봐."로 답한 적이 있다.
    처음 쓰는 도구가 먼저 말을 놓으면 친근한 게 아니라 무례하게 읽힌다.
    """
    reply = (got.get("reply") or "").strip()
    if len(reply) < 10 or _POLITE.search(reply):
        return None
    return f"존댓말 종결이 없다: {reply[:40]}"


def rule_건수(got: dict) -> str | None:
    """답에 적은 건수가 실제 결과와 다르면 안 된다.

    검색 답은 결과로 조립하지만 질문 답은 모델이 쓴다. 표에 없는 숫자가 섞이면
    없는 공고를 있다고 말하는 셈이다.
    """
    total = got.get("total", 0)
    if not total:
        return None
    numbers = {int(n.replace(",", "")) for n in _COUNT.findall(got.get("reply") or "")}
    if numbers and total not in numbers:
        return f"답의 건수 {sorted(numbers)}에 실제 {total}건이 없다"
    return None


def rule_표라는말(got: dict) -> str | None:
    """사용자는 표를 본 적이 없다. "표에 없다"는 말은 무슨 표인지 모를 소리다."""
    reply = got.get("reply") or ""
    if "표에" in reply or "표를 보면" in reply:
        return "답에 '표' 이야기가 나온다"
    return None


def rule_마크다운표(got: dict) -> str | None:
    """대화창은 표를 그리지 않는다. 막대 기호만 줄줄이 나온다."""
    return "마크다운 표를 그렸다" if _MD_TABLE.search(got.get("reply") or "") else None


def rule_인사에안내금지(got: dict) -> str | None:
    return "인사에 사용법 안내가 나갔다" if GUIDE_MARK in (got.get("reply") or "") else None


def rule_범위밖고정문구(got: dict) -> str | None:
    """정해진 말이 그대로 나가야 한다. 모델이 쓴 문장이 새면 안 된다."""
    reply = got.get("reply") or ""
    if OFF_TOPIC_MARK not in reply:
        return f"정해진 거절 문구가 아니다: {reply[:40]}"
    if got.get("jobs"):
        return "범위 밖인데 공고가 붙어 나갔다"
    return None


def rule_면접후결정(got: dict) -> str | None:
    """왜 못 하는지 밝혀야 한다. 그냥 0건이라고 하면 조건을 빼 보라는 말이 나간다."""
    if "면접 후 결정" not in (got.get("reply") or ""):
        return "급여로 줄 세울 수 없는 이유를 밝히지 않았다"
    return None


def rule_ab라벨(got: dict) -> str | None:
    """"A"와 "B"는 프롬프트 안에서 붙인 이름이다. 사용자는 본 적이 없다."""
    return "공고를 A/B로 불렀다" if _AB_LABEL.search(got.get("reply") or "") else None


RULES = {
    "말투": rule_말투,
    "건수": rule_건수,
    "표라는말": rule_표라는말,
    "마크다운표": rule_마크다운표,
    "인사에안내금지": rule_인사에안내금지,
    "범위밖고정문구": rule_범위밖고정문구,
    "면접후결정": rule_면접후결정,
    "ab라벨": rule_ab라벨,
}


def ask(base_url: str, body: dict, timeout: int = 120) -> tuple[dict, float]:
    """챗봇에 한 번 묻는다. (응답, 걸린 초)."""
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        f"{base_url}/api/v1/jobs/chat",
        data=data,
        headers={"Content-Type": "application/json"},
    )
    began = time.time()
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8")), time.time() - began


def _listy(value: Any) -> list[str]:
    return [str(v).strip() for v in (value or []) if str(v).strip()]


def check(expect: dict, sent: dict, got: dict, elapsed: float) -> list[tuple[str, bool, str]]:
    """정답과 대조한다. (항목, 맞았나, 설명)의 목록.

    `expect`에 적지 않은 칸은 보지 않는다. 케이스마다 관심사가 다르고, 모든 칸을
    다 적게 하면 관심 없는 칸이 바뀔 때마다 케이스를 고쳐야 한다.
    """
    out: list[tuple[str, bool, str]] = []
    filters = got.get("filters") or {}

    def add(name: str, ok: bool, detail: str) -> None:
        out.append((name, ok, detail))

    if "mode" in expect:
        add("mode", got.get("mode") == expect["mode"],
            f"{expect['mode']} ↔ {got.get('mode')}")
    if "mode_not" in expect:
        add("mode(아님)", got.get("mode") != expect["mode_not"],
            f"{expect['mode_not']} 이면 안 됨 ↔ {got.get('mode')}")

    for field in ("roles", "skills", "regions", "employment_types", "keywords", "exclude_keywords"):
        want = (expect.get("filters") or {}).get(field)
        if want is None:
            continue
        have = _listy(filters.get(field))
        # 적은 것이 다 들어 있으면 맞은 것으로 본다. 더 뽑는 것은 벌하지 않는다 —
        # "서울 백엔드"에서 keywords 에 무언가 더 담겨도 검색은 여전히 걸린다.
        add(f"조건 {field}", all(w in have for w in want), f"{want} ⊂ {have}")

    if "career_years" in expect:
        add("조건 career_years", filters.get("career_years") == expect["career_years"],
            f"{expect['career_years']} ↔ {filters.get('career_years')}")
    if expect.get("career_years_unset"):
        # 0으로 박으면 연차 미기재 공고가 통째로 빠진다. 안 밝힌 것과 0년차는 다르다.
        add("조건 career_years(없음)", filters.get("career_years") is None,
            f"null 이어야 함 ↔ {filters.get('career_years')}")

    want_career = (expect.get("filters") or {}).get("career")
    if want_career is not None:
        add("조건 career", filters.get("career") == want_career,
            f"{want_career} ↔ {filters.get('career')}")

    if expect.get("roles_not"):
        have = _listy(filters.get("roles"))
        add("조건 roles(아님)", not any(r in have for r in expect["roles_not"]),
            f"{expect['roles_not']} 이 빠져야 함 ↔ {have}")

    if expect.get("filters_empty"):
        empty = not any(_listy(filters.get(f)) for f in
                        ("roles", "skills", "regions", "employment_types", "keywords", "exclude_keywords"))
        empty = empty and filters.get("career", "무관") == "무관"
        add("조건 비우기", empty, f"비어야 함 ↔ {filters}")

    if expect.get("empty_fields"):
        # 이어받으면 안 되는 칸. 새 주제로 묻는 질문에 앞 대화의 지역·키워드가 붙었었다.
        def filled(field: str) -> bool:
            value = filters.get(field)
            if field == "career":
                return (value or "무관") != "무관"
            return bool(_listy(value))

        stale = {f: filters.get(f) for f in expect["empty_fields"] if filled(f)}
        add("이어받지 않을 조건", not stale, f"비어야 함 ↔ {stale}")

    if expect.get("deadline_set"):
        add("마감 조건", filters.get("deadline_within_days") is not None,
            f"숫자여야 함 ↔ {filters.get('deadline_within_days')}")
    if "posted_within_days" in expect:
        # "오늘 올라온"은 0이다. 0과 null을 가려야 해서 참·거짓이 아니라 값으로 본다.
        add("올라온 날 조건", filters.get("posted_within_days") == expect["posted_within_days"],
            f"{expect['posted_within_days']} ↔ {filters.get('posted_within_days')}")
    if expect.get("posted_unset"):
        add("올라온 날 조건(없음)", filters.get("posted_within_days") is None,
            f"null 이어야 함 ↔ {filters.get('posted_within_days')}")

    if expect.get("picked_rank"):
        want_id = (sent.get("last_job_ids") or [None] * 99)[expect["picked_rank"] - 1]
        shown = [j.get("job_id") for j in (got.get("jobs") or [])]
        add("가리킨 공고", bool(want_id) and want_id in shown,
            f"{want_id} ∈ {shown}")

    if expect.get("new_jobs"):
        # "이거 말고"에 같은 공고를 다시 보여 주면서 "다른 공고를 찾았다"고 답한 적이 있다.
        # 앞에서 본 공고가 하나라도 섞이면 틀린 것이다. 비어 있어도 틀린 것이다.
        seen = set(sent.get("seen_job_ids") or [])
        shown = [j.get("job_id") for j in (got.get("jobs") or [])]
        repeated = [job_id for job_id in shown if job_id in seen]
        add("새 공고", bool(shown) and not repeated,
            f"앞에서 본 {len(seen)}건과 겹침 {repeated} · 보여 준 {len(shown)}건")

    if "resume_scope" in expect:
        add("이력서 범위", got.get("resume_scope") == expect["resume_scope"],
            f"{expect['resume_scope']} ↔ {got.get('resume_scope')}")

    if expect.get("polite"):
        # 존댓말은 규율 검사와 같은 것을 본다. 잣대가 둘이면 어느 쪽이 맞는지 모른다.
        detail = rule_말투(got)
        add("규율 말투", detail is None, detail or "존댓말")

    for name in expect.get("rules") or []:
        detail = RULES[name](got)
        add(f"규율 {name}", detail is None, detail or "지킴")

    add("응답 시간", elapsed < 30.0, f"{elapsed:.1f}초")
    return out


# ── 적어 두고 안 보는 칸이 다시 생기지 않게 ────────────────────────

# 응답으로 나오는 것. `check`가 본다.
HTTP_KEYS = frozenset({
    "mode", "mode_not", "filters", "roles_not", "filters_empty",
    "deadline_set", "picked_rank", "resume_scope", "polite", "rules",
    "career_years", "career_years_unset", "new_jobs",
    "posted_within_days", "posted_unset", "empty_fields",
})
# 응답에 안 나오는 것. `check_router`가 본다.
ROUTER_KEYS = frozenset({
    "intent", "topic", "topic_not", "counts_jobs", "job_refs",
    "refers_to_last_answer", "unavailable", "requirement_query_nonempty", "show_more",
})


def unknown_keys(cases: list[dict]) -> set[str]:
    """어느 쪽도 안 보는 칸. 케이스에 적어 두고 안 재던 일이 실제로 있었다."""
    known = HTTP_KEYS | ROUTER_KEYS
    return {
        key
        for case in cases
        for turn in case["turns"]
        for key in (turn.get("expect") or {})
        if key not in known
    }


def load_cases() -> list[dict]:
    cases = json.loads(CASES.read_text(encoding="utf-8"))["cases"]
    unknown = unknown_keys(cases)
    if unknown:
        print(f"  경고: 아무도 안 보는 칸이 있습니다 — {sorted(unknown)}")
    return cases


def check_router(expect: dict, turn: Any) -> list[tuple[str, bool, str]]:
    """말을 가른 결과를 대조한다. 응답에 안 실리는 칸만 여기서 본다."""
    out: list[tuple[str, bool, str]] = []

    def add(name: str, ok: bool, detail: str) -> None:
        out.append((name, ok, detail))

    if "intent" in expect:
        add("갈래 intent", turn.intent == expect["intent"],
            f"{expect['intent']} ↔ {turn.intent}")
    if "topic" in expect:
        add("갈래 topic", turn.topic == expect["topic"],
            f"{expect['topic']} ↔ {turn.topic}")
    if "refers_to_last_answer" in expect:
        add("방금 그거", turn.refers_to_last_answer is expect["refers_to_last_answer"],
            f"{expect['refers_to_last_answer']} ↔ {turn.refers_to_last_answer}")
    if "topic_not" in expect:
        add("갈래 topic(아님)", turn.topic != expect["topic_not"],
            f"{expect['topic_not']} 이면 안 됨 ↔ {turn.topic}")
    if "counts_jobs" in expect:
        add("셀 물음인가", turn.counts_jobs is expect["counts_jobs"],
            f"{expect['counts_jobs']} ↔ {turn.counts_jobs}")
    if "job_refs" in expect:
        add("가리킨 번호", list(turn.job_refs) == list(expect["job_refs"]),
            f"{expect['job_refs']} ↔ {list(turn.job_refs)}")
    if "unavailable" in expect:
        add("없는 정보", turn.unavailable == expect["unavailable"],
            f"{expect['unavailable']} ↔ {turn.unavailable!r}")
    if "show_more" in expect:
        add("더 보기", turn.show_more is expect["show_more"],
            f"{expect['show_more']} ↔ {turn.show_more}")
    if expect.get("requirement_query_nonempty"):
        add("뜻으로 찾을 문장", bool(turn.requirement_query.strip()),
            f"{turn.requirement_query!r}")
    return out


def run_router() -> Path:
    """서버를 안 거치고 라우터만 부른다. 앞 턴이 뽑은 조건을 그대로 잇는다."""
    from job_matching_bot.api import schemas
    from job_matching_bot.api.service import ChatService
    from job_matching_bot.env import ensure_loaded

    # 서버를 안 거치므로 키를 읽어 주는 것도 없다. API가 뜰 때 하는 일을 여기서 한다.
    ensure_loaded()
    route = ChatService().generator
    cases = load_cases()
    results: list[dict] = []
    started = time.time()

    for case in cases:
        previous = schemas.ChatFilters()
        turns: list[dict] = []
        for step in case["turns"]:
            began = time.time()
            turn = route({
                "previous": previous.model_dump_json(),
                "message": step["message"],
            })
            elapsed = time.time() - began
            checks = check_router(step.get("expect") or {}, turn)
            checks.append(("응답 시간", elapsed < 30.0, f"{elapsed:.1f}초"))
            turns.append({
                "message": step["message"],
                "got": json.loads(turn.model_dump_json()),
                "elapsed": elapsed,
                "checks": checks,
            })
            previous = turn.filters

        passed = all(ok for t in turns for _, ok, _ in t["checks"])
        results.append({"id": case["id"], "note": case.get("note", ""),
                        "turns": turns, "passed": passed})
        print(f"  {case['id']:24} {'통과' if passed else '실패'}"
              f"  {sum(t['elapsed'] for t in turns):5.1f}초")

    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    path = RUNS_DIR / f"{time.strftime('%Y%m%d-%H%M%S')}-router.json"
    path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    _report(results, time.time() - started)
    print(f"\n결과 원본: {path}")
    return path


def run(base_url: str) -> Path:
    cases = load_cases()
    results: list[dict] = []
    started = time.time()

    for case in cases:
        filters = None
        last_job_ids: list[str] = []
        seen_job_ids: list[str] = []
        turns: list[dict] = []
        broke = False
        for turn in case["turns"]:
            body = {
                "message": turn["message"],
                "filters": filters,
                "last_job_ids": last_job_ids,
                "seen_job_ids": seen_job_ids,
                "top_k": 5,
            }
            try:
                got, elapsed = ask(base_url, body)
            except urllib.error.URLError as error:
                print(f"  {case['id']}: 서버 호출 실패 — {error}")
                broke = True
                break
            checks = check(turn.get("expect") or {}, body, got, elapsed)
            turns.append({
                "message": turn["message"], "sent": body, "got": got,
                "elapsed": elapsed, "checks": checks,
            })
            # 앱이 하는 것과 같이 앞 턴의 결과를 다음 턴에 실어 보낸다.
            # 본 공고는 조건이 그대로인 동안 쌓고, 조건이 바뀌면 새로 센다(앱 `nextSeenJobIds`).
            if got.get("mode") == "검색" and got.get("jobs"):
                ids = [j["job_id"] for j in got["jobs"]]
                same = got.get("filters") == filters
                seen_job_ids = [*seen_job_ids, *ids] if same else ids
            filters = got.get("filters")
            if got.get("jobs"):
                last_job_ids = [j["job_id"] for j in got["jobs"]]
        if broke:
            break
        passed = all(ok for t in turns for _, ok, _ in t["checks"])
        results.append({"id": case["id"], "note": case.get("note", ""),
                        "turns": turns, "passed": passed})
        mark = "통과" if passed else "실패"
        print(f"  {case['id']:24} {mark}  {sum(t['elapsed'] for t in turns):5.1f}초")

    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    path = RUNS_DIR / f"{stamp}.json"
    path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    _report(results, time.time() - started)
    print(f"\n결과 원본: {path}")
    return path


def _report(results: list[dict], elapsed: float) -> None:
    if not results:
        return
    checks = [(name, ok) for r in results for t in r["turns"] for name, ok, _ in t["checks"]]
    by_kind: dict[str, list[int]] = {}
    for name, ok in checks:
        kind = name.split()[0]
        by_kind.setdefault(kind, [0, 0])
        by_kind[kind][1] += 1
        by_kind[kind][0] += ok

    passed = sum(1 for r in results if r["passed"])
    times = [t["elapsed"] for r in results for t in r["turns"]]
    print(f"\n케이스 {passed}/{len(results)} 통과 · {elapsed:.0f}초")
    print(f"{'항목':16} {'맞음':>8}")
    for kind, (ok, total) in sorted(by_kind.items(), key=lambda x: -x[1][1]):
        print(f"  {kind:14} {ok:>3}/{total:<3} ({ok/total*100:3.0f}%)")
    times.sort()
    print(f"\n응답 시간  중앙값 {times[len(times)//2]:.1f}초 · 최대 {times[-1]:.1f}초")

    failed = [r for r in results if not r["passed"]]
    if failed:
        print("\n어긋난 케이스")
        for r in failed:
            print(f"  {r['id']} — {r['note']}")
            for t in r["turns"]:
                for name, ok, detail in t["checks"]:
                    if not ok:
                        print(f"      “{t['message'][:28]}”  {name}: {detail}")


# ── 사람이 매긴 것을 읽는다 ──────────────────────────────────

LABELS_DIR = FIXTURES_DIR / "labels"


def latest_labels() -> Path | None:
    """가장 최근 챗봇 채점표. 회차마다 한 파일이고 지우지 않는다."""
    found = sorted(LABELS_DIR.glob("chat-*.csv"))
    return found[-1] if found else None


def read_labels(path: Path) -> list[dict[str, str]]:
    # 브라우저가 엑셀용으로 BOM을 붙여 내려준다. utf-8-sig가 그걸 먹는다.
    import csv

    return list(csv.DictReader(path.read_text(encoding="utf-8-sig").splitlines()))


def score(path: Path) -> int:
    """근거와 지어냄을 센다. 숫자 둘이 전부다.

    **지어냄이 있으면 그 건수가 답이다.** 근거율이 아무리 높아도 없는 마감일을
    말하는 답이 섞여 있으면 나머지도 못 믿는다. 그래서 따로 세고 따로 보여 준다.
    """
    rows = read_labels(path)
    if not rows:
        print(f"{path} 가 비었습니다.")
        return 1

    ground = Counter(r.get("근거", "").strip() for r in rows)
    made_up = [r for r in rows if r.get("지어냄", "").strip() == "있음"]
    judged = ground["근거 있음"] + ground["일반론"]

    print(f"\n{path.name} · {len(rows)}건")
    print(f"\n{'근거':16}{'건수':>6}")
    for name in ("근거 있음", "일반론", "해당 없음"):
        print(f"  {name:14}{ground[name]:>6}")
    if judged:
        print(f"\n근거율 {ground['근거 있음'] / judged * 100:.0f}%"
              f"  ({ground['근거 있음']}/{judged})"
              f"  — 공고로 답했어야 하는 {judged}건 중")
    else:
        print("\n공고로 답할 물음이 한 건도 없었습니다.")

    print(f"\n지어냄 {len(made_up)}건")
    for row in made_up:
        note = (row.get("메모") or "").strip()
        print(f"  {row.get('id', '?')} — {row.get('물음', '')[:34]}"
              + (f"\n      {note}" if note else ""))
    return 0


def latest_run() -> Path | None:
    """가장 최근 `--run` 결과. 라우터 결과에는 답 문장이 없으니 세지 않는다."""
    runs = sorted(p for p in RUNS_DIR.glob("*.json") if not p.stem.endswith("-router"))
    return runs[-1] if runs else None


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="챗봇 평가")
    parser.add_argument("--router", action="store_true",
                        help="말을 가른 결과만 대조한다. 서버가 필요 없다")
    parser.add_argument("--run", action="store_true", help="케이스를 돌려 정답과 대조한다")
    parser.add_argument("--sheet", action="store_true", help="답 문장을 사람이 매길 페이지를 만든다")
    parser.add_argument("--score", action="store_true", help="사람이 매긴 채점표를 읽어 센다")
    parser.add_argument("--labels", type=Path, default=None)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--run-file", type=Path, default=None)
    args = parser.parse_args()

    if args.score:
        path = args.labels or latest_labels()
        if path is None:
            print(f"채점표가 없습니다. --sheet 로 매긴 뒤 {LABELS_DIR} 에 두세요.")
            return 1
        return score(path)
    if args.router:
        run_router()
        return 0
    if args.run:
        run(args.base_url)
        return 0
    if args.sheet:
        from job_matching_bot.evaluation.chat_grader_page import write_page

        path = args.run_file or latest_run()
        if path is None:
            print("먼저 --run 으로 결과를 만드세요.")
            return 1
        if path.stem.endswith("-router"):
            print("라우터 결과에는 답 문장이 없습니다. --run 결과를 주세요.")
            return 1
        results = json.loads(path.read_text(encoding="utf-8"))
        page = write_page(path.with_name(path.stem + "-채점.html"), results)
        print(f"채점 페이지: {page}   ← 답 문장만 매기면 된다")
        return 0

    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
