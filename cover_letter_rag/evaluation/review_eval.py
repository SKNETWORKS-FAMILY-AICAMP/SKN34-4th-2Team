"""공고 맞춤 첨삭을 목업 이력서로 처음부터 끝까지 돌려 본다.

첫 첨삭 → 질문마다 답변 → 그 항목 재첨삭 → 누락 점검까지, 앱이 서버에 보내는 요청을
그대로 만든다. 첨삭 코드(`run_review`)는 손대지 않고 Firestore만 메모리로 바꾼다. 공고도
SQLite가 아니라 케이스에 적힌 지어낸 공고를 쓴다(실제 공고는 마감되면 사라진다).

답변은 "지원자 역할" 모델이 케이스의 `applicant.facts`(실제로 한 일)와 `not_done`(해 본 적
없는 것)만 보고 쓴다. 그래서 첨삭 결과에 이 두 목록과 이력서 어디에도 없는 사실이 들어가면
첨삭이 지어낸 것이다.

    cd cover_letter_rag
    python -m evaluation.review_eval --cases dev --label baseline
    python -m evaluation.review_eval --cases dev --only weak_backend__si --max-questions 3

결과는 evaluation/runs/<시각>_<label>/ 에 results.json, 케이스별 대화 기록(.md)으로 남는다.
실제 모델을 부르므로 비용이 든다. 케이스 하나에 모델 호출이 대략 (질문 수 + 2)번 + 답변 수만큼이다.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path

HERE = Path(__file__).resolve().parent
SERVICE_ROOT = HERE.parent
REPO_ROOT = SERVICE_ROOT.parent
for path in (str(SERVICE_ROOT), str(REPO_ROOT)):
    if path not in sys.path:
        sys.path.insert(0, path)

from langchain_openai import ChatOpenAI  # noqa: E402

import app.matching_handoff as matching_handoff  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.models import ConfirmationAnswer, FirestoreResumeReviewRequest  # noqa: E402
from app.resume_review import ResumeReviewService, _answer_is_reflected, extract_review_fields  # noqa: E402
from app.review_workflow import MISSING_JOB_TECH_REASON, ReviewInputError, digest, group, job_role_title  # noqa: E402
from app.technology import grounding_terms  # noqa: E402

COHORT, RESUME, TAILORED, UID = "eval-cohort", "eval-resume", "eval-tailored", "eval-user"
THIN_QUESTION = "문항에서 본인이 직접 한 행동이나 경험을 조금 더"
GENERIC_FALLBACK = "원문 의미를 유지하기 위해"
NEGATIVE_ANSWER = re.compile(r"(경험은?\s*없|해\s*본\s*적\s*없|없어요|없습니다|모르겠|기억나지\s*않)")
# 지원 자격을 묻는 질문. 답해도 이력서 문장으로 고칠 게 없다. 서버 규칙과 따로 평가 쪽에서 넓게 잡는다.
ELIGIBILITY_QUESTION = re.compile(
    r"(신입|경력\s*\d|경력\s*(?:으로)?\s*인정|\d+\s*(?:년|개월)\s*(?:이하|이상|미만)|학력|졸업|학위|전공|병역|군\s*복무|면허|"
    r"근무(?:가|를|는)?\s*가능|풀타임|출근|입사\s*가능|근무\s*지역|지원\s*지역|거주)"
)
# 사용자에게 보이는 문장에 새어 나온 내부 이름.
INTERNAL_TERM = re.compile(
    r"(field_path|필드\s*경로|requirement_id|edit_type|\b(?:coreCompetencies|selfIntroduction|trainingExperience|"
    r"otherActivities|techStack|projects|experience|awards|certifications|education)(?:\[\d+\])?\.[A-Za-z]+)"
)
STAR_KEYS = {"S": "situation", "T": "task", "A": "action", "R": "result"}


def is_negative_answer(answer: str) -> bool:
    """답 전체가 "없다·모른다"인 경우만. "pyserial로 작성했습니다. 시간 변화는 잰 적 없어요"처럼 사실이
    섞인 답은 사실 부분을 반영하는 게 맞으므로 부정 답으로 세지 않는다."""
    sentences = [part for part in re.split(r"(?<=[.!?요다])\s+", answer.strip()) if part.strip()]
    return bool(sentences) and all(NEGATIVE_ANSWER.search(part) for part in sentences)


# ── 케이스 ────────────────────────────────────────────────────────────────

def load_cases(name: str) -> list[dict]:
    path = HERE / "fixtures" / f"review_cases_{name}.json"
    cases = json.loads(path.read_text(encoding="utf-8"))["cases"]
    for case in cases:
        persona = case["persona"]
        if "content" in persona:
            case["content"] = persona["content"]
        else:
            source = json.loads((REPO_ROOT / persona["source"]).read_text(encoding="utf-8"))
            case["content"] = source["personas"][persona["key"]]["content"]
    return cases


def selected_job(case: dict) -> dict:
    """matching_handoff.load_selected_job과 같은 모양으로 공고를 만든다."""
    job = case["job"]
    text = f"회사: {job['company']}\n공고: {job['title']}\n\n{job['text']}"
    source = {
        "job_id": job["job_id"],
        "company": job["company"],
        "title": job["title"],
        "source_url": "",
        "content_hash": digest(text),
        "deadline": "",
    }
    source["role_title"] = job_role_title(source["company"], source["title"])
    source["snapshot_hash"] = digest([source, text, "OPEN"])
    return {"text": text, "source": source}


# 첨삭 흐름은 공고를 SQLite에서 job_id로 읽는다. 케이스를 동시에 돌리므로 함수를 케이스마다
# 바꿔 끼우지 않고, job_id로 찾아 주는 함수 하나를 처음에 끼워 둔다.
JOBS: dict[str, dict] = {}
REQUIREMENT_CACHE: dict[str, list] = {}
matching_handoff.load_selected_job = lambda _path, job_id: JOBS[job_id]


class MemoryGateway:
    """첨삭 흐름이 부르는 Firestore 메서드만 메모리로 흉내 낸다. 아무것도 쓰지 않는다."""

    def __init__(self, content: dict, job: dict) -> None:
        self.content = deepcopy(content)
        self.job = job
        self.states: dict[str, dict] = {}

    def verify_id_token(self, _token):
        return UID

    def _doc(self):
        return {
            "userId": UID,
            "content": self.content,
            "jobId": self.job["source"]["job_id"],
            "jobSnapshotHash": self.job["source"]["snapshot_hash"],
        }

    def get_owned_tailored_resume(self, *_args):
        return self._doc()

    def get_owned_resume(self, *_args):
        return self._doc()

    def claim_review(self, _c, _r, _u, request_id, fingerprint, _t=None):
        state = self.states.setdefault(request_id, {"fingerprint": fingerprint})
        return state if state.get("response") else {}

    def complete_review(self, _c, _r, _u, request_id, response, _t=None):
        self.states[request_id]["response"] = response

    def fail_review(self, *_args, **_kwargs):
        pass

    def get_ai_review(self, _c, _r, _u, review_id, _t=None):
        return self.states[review_id]["response"]

    # 요건 정리 결과는 케이스 안에서만 재사용한다(Firestore에 남기지 않는다).
    def get_job_requirements(self, key):
        return REQUIREMENT_CACHE.get(key)

    def save_job_requirements(self, key, requirements):
        REQUIREMENT_CACHE[key] = requirements


# ── 지원자 역할 ───────────────────────────────────────────────────────────

APPLICANT_SYSTEM = """너는 이력서 첨삭 챗봇의 질문에 답하는 지원자다.
[내가 실제로 한 일]과 [해 본 적 없는 것]만 근거로 답한다. 새 사실을 지어내지 않는다.

- 질문과 관련된 내용이 [내가 실제로 한 일]에 있으면 그 내용만 한국어 1~2문장으로 답한다.
- 질문이 어느 프로젝트에서 했는지 물으면 이력서의 프로젝트 이름을 답에 꼭 넣는다.
- 관련 내용이 [내가 실제로 한 일]에 없거나 [해 본 적 없는 것]에 해당하면 "그런 경험은 없어요."라고만 답한다.
- 이미 이력서에 적힌 내용을 다시 묻는 질문이면, [내가 실제로 한 일]에 더할 사실이 있을 때만 답하고 없으면 "이력서에 적은 것 외에 더 한 건 없어요."라고 답한다.
"""


# 사람 답변 모드(--applicant human). 목업 답은 항목 이름을 또박또박 넣은 완결 문장이라, 실제 학생 답에서 흔한 모양을
# 서버가 어떻게 받는지 보지 못했다. 답의 근거는 그대로 [내가 실제로 한 일]·[해 본 적 없는 것]만 쓰고 모양만 바꾼다.
HUMAN_TRAITS = {
    "short": "한 줄로 짧게 답한다. 문장을 끝맺지 않아도 된다(예: '네 pytest로 40개 정도 짰어요').",
    "nickname": "항목 이름을 정확히 쓰지 않고 줄이거나 대충 부른다(예: '그 챗봇', '전 회사', '졸작').",
    "other_item": "질문한 항목 말고 [내가 실제로 한 일]에 있는 다른 항목 이야기도 한 가지 같이 한다.",
    "not_done_tail": "사실을 말한 뒤 [해 본 적 없는 것] 중 질문과 가까운 것을 '그건 안 해 봤어요'처럼 덧붙인다.",
    "typo": "줄임말·띄어쓰기·맞춤법을 대충 쓴다(예: '했었는데여', '구현햇어요', 'api 연동함').",
    "uncertain": "사실 하나를 '잘 모르겠는데 아마', '~였던 것 같아요'처럼 확신 없이 말한다. 없는 사실을 만들지는 않는다.",
}

APPLICANT_HUMAN_SYSTEM = """너는 이력서 첨삭 챗봇의 질문에 채팅으로 답하는 실제 취업 준비생이다.
[내가 실제로 한 일]과 [해 본 적 없는 것]만 근거로 답한다. 새 사실·숫자·기술·역할을 지어내지 않는다.

- 질문과 관련된 내용이 [내가 실제로 한 일]에 있으면 그 사실로 답한다. 없거나 [해 본 적 없는 것]이면 '안 해봤어요', '없어요'처럼 짧게 답한다.
- 이번 답에서는 [말투 지시]를 따른다. 말투는 바꿔도 사실은 바꾸지 않는다.
- 설명·머리말 없이 답 문장만 쓴다.
"""


def _human_traits(case_id: str, question: str) -> list[str]:
    """케이스·질문마다 같은 말투 한두 개를 고른다(다시 돌려도 같은 조합)."""
    seed = int(hashlib.sha256(f"{case_id}|{question}".encode("utf-8")).hexdigest(), 16)
    names = list(HUMAN_TRAITS)
    first = names[seed % len(names)]
    picked = [first]
    if (seed // 7) % 2:
        second = names[(seed // 11) % len(names)]
        if second != first:
            picked.append(second)
    return picked


def make_applicant(settings, style: str = "mock"):
    model = ChatOpenAI(
        model=settings.openai_model,
        api_key=settings.openai_api_key,
        use_responses_api=True,
        reasoning_effort="low",
        max_retries=2,
    )
    traits_by_turn: dict[tuple[str, str], list[str]] = {}

    def answer(case: dict, question: str) -> str:
        projects = ", ".join(p.get("name", "") for p in case["content"].get("projects", []))
        facts = "\n".join(f"- {fact}" for fact in case["applicant"]["facts"])
        not_done = "\n".join(f"- {item}" for item in case["applicant"]["not_done"])
        body = (f"[이력서 프로젝트 이름]\n{projects}\n\n[내가 실제로 한 일]\n{facts}\n\n"
                f"[해 본 적 없는 것]\n{not_done}\n\n[챗봇 질문]\n{question}")
        system = APPLICANT_SYSTEM
        if style == "human":
            traits = _human_traits(case["id"], question)
            traits_by_turn[(case["id"], question)] = traits
            system = APPLICANT_HUMAN_SYSTEM
            body += "\n\n[말투 지시]\n" + "\n".join(f"- {HUMAN_TRAITS[t]}" for t in traits)
        message = model.invoke([("system", system), ("human", body)])
        content = message.content
        if isinstance(content, list):
            content = "".join(part.get("text", "") for part in content if isinstance(part, dict))
        return str(content).strip()

    answer.traits_for = lambda case_id, question: traits_by_turn.get((case_id, question))
    return answer


# ── 판정 도우미 ───────────────────────────────────────────────────────────

_UNITS = {"s": "초", "sec": "초", "초": "초", "ms": "ms", "min": "분", "분": "분", "시간": "시간", "h": "시간",
          "%": "%", "%p": "%p", "건": "건", "개": "개", "명": "명", "배": "배", "만": "만", "년": "년", "개월": "개월"}
_NUMBER = re.compile(r"(\d+(?:[.,]\d+)*)\s*(%p|%|ms|sec|min|s|h|초|분|시간|건|개월|개|명|배|만|년)?")


def numbers(text: str) -> set[str]:
    """숫자를 값 기준으로 모은다. 1.2s와 1.2초, 1,000과 1000을 같게 본다. 평가 전용 느슨한 비교다."""
    found = set()
    for value, _unit in _NUMBER.findall(text or ""):
        value = value.replace(",", "")
        try:
            found.add(str(float(value)))
        except ValueError:
            continue
    return found


def classify_question(question: dict, earlier: list[dict]) -> str:
    text = question.get("question", "").strip()
    if text in {"없음", "없습니다", "-"} or len(text) < 5:
        return "empty"
    if THIN_QUESTION in text:
        return "template"
    if GENERIC_FALLBACK in text:
        return "fallback"
    if question.get("requirement_id"):
        return "requirement"
    for other in earlier:
        if other.get("field_path") == question.get("field_path") and \
                SequenceMatcher(None, other.get("question", ""), text).ratio() > 0.7:
            return "duplicate"
    if question.get("reason") == MISSING_JOB_TECH_REASON or "공고" in text:
        return "job"
    return "model"


def visible_questions(review: dict, limit: int = 7) -> list[dict]:
    rows, seen = [], []
    for question in review.get("questions", [])[:limit]:
        rows.append({**question, "kind": classify_question(question, seen)})
        seen.append(question)
    return rows


# ── 한 케이스 ─────────────────────────────────────────────────────────────

def run_case(case: dict, settings, applicant, max_questions: int, generator=None, apply_polish: bool = False) -> dict:
    job = selected_job(case)
    gateway = MemoryGateway(case["content"], job)
    service = ResumeReviewService(settings, gateway, generator)
    fields, _ = extract_review_fields(case["content"])
    resume_text = "\n".join(fields.values())
    answers_so_far: list[str] = []
    turns: list[dict] = []
    record = {"id": case["id"], "company": case["job"]["company"], "title": case["job"]["title"], "errors": []}

    def request(**extra):
        return FirestoreResumeReviewRequest(
            cohort_id=COHORT, resume_id=RESUME, review_mode="job", tailored_resume_id=TAILORED,
            selected_job_id=case["job"]["job_id"], **extra,
        )

    JOBS[case["job"]["job_id"]] = job
    started = time.monotonic()
    first = service.review("eval-token", request()).model_dump()
    record["first"] = summarize_review(first, fields)
    current = first
    if apply_polish:
        current, record["polish"] = apply_polish_bundle(gateway, first)
        fields, _ = extract_review_fields(gateway.content)
    asked: set[str] = set()

    for _ in range(max_questions):
        question = next(
            (q for q in current.get("questions", [])
             if re.sub(r"\W", "", q["question"]) not in asked),
            None,
        )
        if question is None:
            break
        asked.add(re.sub(r"\W", "", question["question"]))
        answer = applicant(case, question["question"])
        answers_so_far.append(answer)
        turn = {"field_path": question["field_path"], "question": question["question"],
                "kind": classify_question(question, []), "answer": answer,
                "negative": is_negative_answer(answer)}
        traits_for = getattr(applicant, "traits_for", None)
        if traits_for and traits_for(case["id"], question["question"]):
            turn["answer_traits"] = traits_for(case["id"], question["question"])
        try:
            follow = service.review("eval-token", request(
                previous_review_id=current["review_id"],
                expected_input_hash=current["input_hash"],
                answers=[ConfirmationAnswer(
                    question_id=question["question_id"], field_path=question["field_path"],
                    question=question["question"], answer=answer,
                )],
            )).model_dump()
        except (ReviewInputError, Exception) as exc:  # 한 질문 실패가 대화를 멈추지 않게
            turn["error"] = f"{type(exc).__name__}: {exc}"[:200]
            record["errors"].append(turn["error"])
            turns.append(turn)
            continue
        summary = summarize_review(follow, fields)
        turn["elapsed_ms"] = (follow.get("telemetry") or {}).get("elapsed_ms")
        # resume-v16u부터: 후속 첨삭에서 사실 검사 모델을 부른 수·걸린 시간·안내가 붙은 수.
        follow_telemetry = follow.get("telemetry") or {}
        turn["fact_checks"] = follow_telemetry.get("fact_checks")
        turn["fact_check_ms"] = follow_telemetry.get("fact_check_ms")
        turn["fact_notices"] = follow_telemetry.get("fact_notices")
        turn["requirement_id"] = question.get("requirement_id")
        turn["topic"] = question.get("topic")
        before = {row["id"]: row["status"] for row in current.get("requirement_map") or []}
        after = {row["id"]: row["status"] for row in follow.get("requirement_map") or []}
        turn["requirement_changed"] = before != after
        # 앱은 재첨삭 결과 중 방금 답한 항목의 수정안만 보여준다. 이전 수정안이 다시 딸려 와도 세지 않는다.
        answered_group = group(question["field_path"])
        turn["suggestions"] = [s for s in summary["suggestions"] if group(s["field_path"]) == answered_group]
        # 묶음 적용 뒤라면 재첨삭 수정안의 원문이 "다듬어진 최신 문장"에서 나와야 한다.
        turn["quotes_on_latest_text"] = all(
            re.sub(r"\s+", "", s["original"]) in re.sub(r"\s+", "", fields.get(s["field_path"], ""))
            for s in turn["suggestions"]
        )
        turn["dropped"] = [d for d in summary["dropped"] if group(d["field_path"]) == answered_group]
        turn["warnings"] = [w for w in summary["warnings"] if question["field_path"].split("[")[0] in w]
        turn["reflected"] = any(
            _answer_is_reflected(s["original"], s["revision"], answer) for s in summary["suggestions"]
        )
        # resume-v16d부터 앱은 질문 칸이 아니라 서버가 답을 옮긴 칸(응답 confirmed_answers의 field_path)의 수정안을
        # 보여 준다. 위 suggestions는 예전 앱처럼 질문 칸 기준이라 비교용으로 두고, 앱에 실제로 보이는 것을 따로 남긴다.
        moved = next((a.get("field_path") for a in reversed(follow.get("confirmed_answers") or [])
                      if a.get("answer") == answer), question["field_path"])
        turn["moved_to"] = moved
        # resume-v16p부터: 답에 다른 항목 이름이 나오면 그 항목도 함께 고치고 answer_scope_paths에 싣는다. 앱은 답한 칸 다음에 그 칸 수정안도 보여 준다.
        turn["scope_paths"] = [p for p in (follow.get("answer_scope_paths") or []) if group(p) != group(moved)]
        shown_groups = {group(moved), *(group(p) for p in turn["scope_paths"])}
        turn["suggestions_shown"] = [s for s in summary["suggestions"] if group(s["field_path"]) in shown_groups]
        turn["scope_suggestions"] = [s for s in turn["suggestions_shown"] if group(s["field_path"]) != group(moved)]
        turn["scope_dropped"] = [d for d in summary["dropped"]
                                 if group(d["field_path"]) in shown_groups and group(d["field_path"]) != group(moved)]
        # 새 프로젝트 제안은 아직 없는 칸(projects[N])이라 위 기준으로는 안 잡힌다. 앱은 "새 프로젝트로 추가" 카드로 보여 준다.
        new_items = [s for s in summary["suggestions"] if s.get("new_item") and s not in turn["suggestions_shown"]]
        turn["suggestions_shown"] += new_items
        turn["new_items"] = new_items
        turns.append(turn)
        current = follow

    try:
        gap = service.review("eval-token", request(
            review_phase="gap_audit", previous_review_id=current["review_id"],
        )).model_dump()
        record["gap_audit"] = {"elapsed_ms": (gap.get("telemetry") or {}).get("elapsed_ms"),
                               "new_questions": [q["question"] for q in gap.get("questions", [])[:5]]}
    except Exception as exc:  # noqa: BLE001
        record["errors"].append(f"gap_audit {type(exc).__name__}: {exc}"[:200])

    record["turns"] = turns
    record["final_requirement_map"] = current.get("requirement_map") or []
    record["requirement_score"] = score_requirements(case, record["first"].get("requirement_map") or [])
    record["star_score"] = score_star(case, record["first"].get("star_checks"))
    record["question_quality"] = question_quality(case, record)
    record["total_s"] = round(time.monotonic() - started, 1)
    record["fabrication"] = fabrication_checks(case, resume_text, answers_so_far, record)
    return record


def apply_polish_bundle(gateway, review: dict) -> tuple[dict, dict]:
    """앱의 "문장 다듬기 묶음 적용"을 흉내 낸다. 서버 적용 코드(build_application·rebase)를 그대로 쓴다."""
    from types import SimpleNamespace

    from app.resume_apply import build_application, rebase_review_response

    indices = [i for i, s in enumerate(review.get("sentence_reviews", []))
               if s.get("suggested_revision") and s.get("edit_type") in {"spelling", "tone", "clarity"}]
    info = {"offered": len(indices), "applied": 0, "error": None}
    if not indices:
        return review, info
    try:
        updated, _ = build_application(
            gateway.content, review, SimpleNamespace(expected_input_hash=review["input_hash"], selected_indices=indices))
    except Exception as exc:  # noqa: BLE001
        info["error"] = f"{type(exc).__name__}: {exc}"[:200]
        return review, info
    gateway.content = updated
    rebased = rebase_review_response(review, updated)
    gateway.states[review["review_id"]]["response"] = rebased
    info["applied"] = len(indices)
    return rebased, info


def summarize_review(review: dict, fields: dict) -> dict:
    telemetry = review.get("telemetry") or {}
    sentences = review.get("sentence_reviews", [])
    return {
        "elapsed_ms": telemetry.get("elapsed_ms"),
        "requirements_ms": telemetry.get("requirements_ms"),
        "input_tokens": telemetry.get("input_tokens"),
        "output_tokens": telemetry.get("output_tokens"),
        # resume-v16s부터: 첫 첨삭에 준 명사형으로 끊긴 문장 수와 그중 수정안으로 잇지 못한 수.
        "noun_fragments": telemetry.get("noun_fragments"),
        "noun_fragments_unjoined": telemetry.get("noun_fragments_unjoined"),
        "summary": review.get("summary", ""),
        "questions_total": len(review.get("questions", [])),
        "visible": [{"field_path": q["field_path"], "kind": q["kind"], "stage": q.get("stage"), "question": q["question"]}
                    for q in visible_questions(review)],
        "suggestions": [
            {"field_path": s["field_path"], "edit_type": s.get("edit_type"), "status": s.get("status"),
             "original": s["original_quote"], "revision": s["suggested_revision"], "reason": s.get("reason", ""),
             # resume-v16i부터: 다른 칸과 비슷한 문장이면 서버가 안내 문구를 붙인다(거의 같으면 보류돼 dropped로 간다).
             "overlap_notice": s.get("overlap_notice"),
             # resume-v16k부터: 받을 칸이 없는 경험은 새 프로젝트로 제안한다(원문이 비어 있다).
             "new_item": s.get("new_item"),
             # resume-v16m부터: 원문의 바람·목적 부정 표현("겪지 않는")이 빠지면 막지 않고 뜻 확인 안내를 붙인다.
             "meaning_notice": s.get("meaning_notice"),
             # resume-v16u부터: 원문 사실이 빠지거나 약해졌는지 검사 모델이 본 안내, 답을 원문 뒤에 따로 붙인 수정안 안내.
             "fact_notice": s.get("fact_notice"),
             "flow_notice": s.get("flow_notice")}
            for s in sentences if s.get("suggested_revision")
        ],
        "dropped": [
            {"field_path": s["field_path"], "issues": s.get("validation_issues"), "original": s["original_quote"]}
            for s in sentences if s.get("validation_issues")
        ],
        "warnings": review.get("grounding_warnings", []),
        "sentences": [
            {"field_path": s["field_path"], "status": s.get("status"), "edit_type": s.get("edit_type"),
             "has_revision": bool(s.get("suggested_revision")), "reason": (s.get("reason") or "")[:80],
             "issues": s.get("validation_issues")}
            for s in sentences
        ],
        "requirement_map": review.get("requirement_map"),
        "star_checks": review.get("star_checks"),
    }


_EXPECTED_STATUS = {"ok": "met", "partial": "partial", "missing": "unconfirmed"}


def _label_similarity(a: str, b: str) -> float:
    squash = lambda text: re.sub(r"[\s·/,()]+", "", text).casefold()  # noqa: E731
    a, b = squash(a), squash(b)
    if a and b and (a in b or b in a):
        return 1.0
    return SequenceMatcher(None, a, b).ratio()


def score_requirements(case: dict, rows: list[dict]) -> dict:
    """사람이 매긴 기대 판정(expected_requirements)과 첫 첨삭의 요건 표를 견준다.

    이름이 가장 비슷한 요건끼리 짝을 짓는다(0.45 미만이면 못 찾은 것). 가장 위험한 틀림은 이력서에
    근거가 없는데 met으로 본 것(over_claim)이다. 사용자가 없는 경험을 있는 것으로 믿게 된다.
    """
    expected = case.get("expected_requirements") or []
    found, agree, over_claim, pairs = 0, 0, 0, []
    used = set()
    for item in expected:
        best, best_score = None, 0.0
        for index, row in enumerate(rows):
            if index in used:
                continue
            score = _label_similarity(item["label"], row["label"])
            if score > best_score:
                best, best_score = index, score
        if best is None or best_score < 0.45:
            pairs.append({"expected": item["label"], "found": None})
            continue
        used.add(best)
        row = rows[best]
        found += 1
        want = _EXPECTED_STATUS[item["resume"]]
        agree += row["status"] == want
        # 지원 자격(kind=eligibility)은 질문하지 않는 요건이라, "관련 전공"이 근거 있음으로 나와도 없는 경험을 믿게 하지 않는다.
        over_claim += item["resume"] == "missing" and row["status"] == "met" and item.get("kind") != "eligibility"
        pairs.append({"expected": item["label"], "want": want, "found": row["label"], "got": row["status"]})
    return {"expected": len(expected), "extracted": len(rows), "found": found, "status_agree": agree,
            "over_claim": over_claim, "pairs": pairs}


def score_star(case: dict, checks: list[dict] | None) -> dict | None:
    """첫 첨삭의 STAR 판정을 기대 판정과 요소별로 견준다. 판정이 없는 기록(v15 이전)은 None.

    over_claim: 원문에 없는 행동·결과를 있다고 본 것. 이러면 서버가 필요한 질문을 거른다.
    """
    expected = case.get("expected_star") or {}
    if checks is None or not expected:
        return None
    by_path = {c["field_path"]: set(c.get("present") or []) for c in checks}
    score = {"items": len(expected), "judged": 0, "AR_agree": 0, "AR_total": 0, "ST_agree": 0, "ST_total": 0,
             "AR_over_claim": 0, "AR_under_claim": 0, "pairs": []}
    for path, letters in expected.items():
        if path not in by_path:
            score["pairs"].append({"field_path": path, "want": letters, "got": None})
            continue
        score["judged"] += 1
        present = by_path[path]
        got = "".join(k for k, v in STAR_KEYS.items() if v in present)
        score["pairs"].append({"field_path": path, "want": letters, "got": got})
        for key, element in STAR_KEYS.items():
            want, have = key in letters, element in present
            bucket = "AR" if key in "AR" else "ST"
            score[f"{bucket}_total"] += 1
            score[f"{bucket}_agree"] += want == have
            if bucket == "AR" and have and not want:
                score["AR_over_claim"] += 1
            if bucket == "AR" and want and not have:
                score["AR_under_claim"] += 1
    return score


def question_quality(case: dict, record: dict) -> dict:
    """앱에 보이는 질문(첫 첨삭 7개 + 대화에서 실제로 받은 질문)의 헛질문·이미 적힌 항목 질문·내부 용어를 센다.

    질문 문장과 항목 위치만 보므로 STAR 판정이 없던 옛 기록에도 같은 방식으로 셀 수 있다(--rescore).
    - eligibility_questions: 지원 자격을 묻는 질문(경력 연수·학력·근무 조건 등).
    - already_written_questions: 기대 판정에서 행동·결과가 모두 있는 칸에 요건과 무관하게 붙은 질문.
    - wasted_answers: 사실을 답했는데 수정안이 없고 요건 표도 바뀌지 않은 턴.
    - internal_terms: 질문·이유·요약·수정 이유·STAR 안내에 보인 내부 이름.
    """
    expected = case.get("expected_star") or {}
    first = record["first"]
    shown, seen = [], set()
    for q in first["visible"]:
        key = re.sub(r"\W", "", q["question"])
        if key not in seen:
            seen.add(key)
            shown.append({"field_path": q["field_path"], "question": q["question"], "kind": q["kind"]})
    for t in record["turns"]:
        key = re.sub(r"\W", "", t["question"])
        if key not in seen:
            seen.add(key)
            shown.append({"field_path": t["field_path"], "question": t["question"], "kind": t["kind"]})
    eligibility = [q["question"] for q in shown if ELIGIBILITY_QUESTION.search(q["question"])]
    already = [q["question"] for q in shown
               if q["kind"] != "requirement" and set("AR") <= set(expected.get(q["field_path"], ""))]
    # 앱이 보여 주는 수정안(답을 옮긴 칸 기준, resume-v16d부터 기록)이 없을 때만 헛답이다. 예전 기록은 질문 칸 기준으로 센다.
    wasted = [t["question"] for t in record["turns"]
              if "error" not in t and not t["negative"]
              and not (t["suggestions_shown"] if "suggestions_shown" in t else t.get("suggestions"))
              and not t.get("requirement_changed")]
    texts = [q["question"] for q in shown] + [first.get("summary") or ""]
    texts += [s.get("reason") or "" for s in first["suggestions"]]
    texts += [s.get("reason") or "" for t in record["turns"] for s in t.get("suggestions", [])]
    texts += [c.get("reason") or "" for c in first.get("star_checks") or []]
    internal = [m.group(0) for text in texts for m in INTERNAL_TERM.finditer(text)]
    return {"shown": len(shown), "eligibility_questions": eligibility, "already_written_questions": already,
            "wasted_answers": wasted, "internal_terms": internal}


def fabrication_checks(case: dict, resume_text: str, answers: list[str], record: dict) -> dict:
    # 회사명·직무명은 사용자가 고른 공고의 확정값이라 수정안에 들어가도 지어낸 것이 아니다.
    source = selected_job(case)["source"]
    evidence = "\n".join([resume_text, *answers, source["company"], source["title"], source["role_title"]])
    evidence_numbers = numbers(evidence)
    evidence_terms = grounding_terms(evidence)
    suggestions, seen = [], set()
    for s in [*record["first"]["suggestions"], *(s for t in record["turns"] for s in t.get("suggestions", []))]:
        if (s["field_path"], s["revision"]) not in seen:
            seen.add((s["field_path"], s["revision"]))
            suggestions.append(s)
    new_numbers, new_terms, not_done_leaks = [], [], []
    for s in suggestions:
        extra_numbers = numbers(s["revision"]) - evidence_numbers
        if extra_numbers:
            new_numbers.append({"revision": s["revision"][:160], "numbers": sorted(extra_numbers)})
        extra_terms = grounding_terms(s["revision"]) - evidence_terms
        if extra_terms:
            new_terms.append({"revision": s["revision"][:160], "terms": sorted(extra_terms)})
        for item in case["applicant"]["not_done"]:
            position = s["revision"].find(item)
            # "결제 개발 경험은 없지만"처럼 없다고 밝힌 문장은 지어낸 게 아니다(이력서에 적는 게 좋지는 않다).
            negated = position >= 0 and re.search(r"(없|않|못)", s["revision"][position:position + len(item) + 12])
            if position >= 0 and not negated and item not in s["original"] and item not in resume_text:
                not_done_leaks.append({"item": item, "revision": s["revision"][:160]})
    absence_written = [s["revision"][:160] for s in suggestions if re.search(r"경험(?:은|이)?\s*없(?:지만|으나|는데)", s["revision"])]
    return {"new_numbers": new_numbers, "new_terms": new_terms, "not_done_leaks": not_done_leaks,
            "absence_written": absence_written}


# ── 요약·저장 ─────────────────────────────────────────────────────────────

def aggregate(records: list[dict]) -> dict:
    ok = [r for r in records if "first" in r]
    kinds = Counter(q["kind"] for r in ok for q in r["first"]["visible"])
    answered = [t for r in ok for t in r["turns"] if "error" not in t]
    positive = [t for t in answered if not t["negative"]]
    negative = [t for t in answered if t["negative"]]
    mean = lambda xs: round(sum(xs) / len(xs), 1) if xs else None  # noqa: E731
    return {
        "cases": len(records),
        "failed_cases": len(records) - len(ok),
        "first_review_s": mean([r["first"]["elapsed_ms"] / 1000 for r in ok if r["first"]["elapsed_ms"]]),
        "first_output_tokens": mean([r["first"]["output_tokens"] for r in ok if r["first"]["output_tokens"]]),
        "followup_s": mean([t["elapsed_ms"] / 1000 for t in answered if t.get("elapsed_ms")]),
        "case_total_s": mean([r["total_s"] for r in ok]),
        "first_suggestions": mean([len(r["first"]["suggestions"]) for r in ok]),
        "first_dropped": mean([len(r["first"]["dropped"]) for r in ok]),
        "visible_question_kinds": dict(kinds),
        "answers": len(answered),
        "positive_answers_with_suggestion": f"{sum(1 for t in positive if t['suggestions'])}/{len(positive)}",
        "positive_answers_reflected": f"{sum(1 for t in positive if t['reflected'])}/{len(positive)}",
        "negative_answers_with_content_edit": sum(
            1 for t in negative for s in t["suggestions"] if s["edit_type"] == "content"),
        "turn_errors": sum(len(r["errors"]) for r in ok),
        "polish_offered_applied": (
            f'{sum(r["polish"]["offered"] for r in ok if r.get("polish"))}/'
            f'{sum(r["polish"]["applied"] for r in ok if r.get("polish"))}'
        ) if any(r.get("polish") for r in ok) else None,
        "polish_apply_errors": [r["polish"]["error"] for r in ok if r.get("polish") and r["polish"]["error"]],
        "followup_quotes_on_latest_text": (
            f'{sum(1 for r in ok for t in r["turns"] if t.get("suggestions") and t.get("quotes_on_latest_text"))}/'
            f'{sum(1 for r in ok for t in r["turns"] if t.get("suggestions"))}'
        ),
        "fabricated_numbers": sum(len(r["fabrication"]["new_numbers"]) for r in ok),
        "fabricated_terms": sum(len(r["fabrication"]["new_terms"]) for r in ok),
        "not_done_leaks": sum(len(r["fabrication"]["not_done_leaks"]) for r in ok),
        "absence_written_in_resume": sum(len(r["fabrication"].get("absence_written", [])) for r in ok),
        "requirements_expected": sum(r["requirement_score"]["expected"] for r in ok),
        "requirements_found": sum(r["requirement_score"]["found"] for r in ok),
        "requirement_status_agree": sum(r["requirement_score"]["status_agree"] for r in ok),
        "requirement_over_claim": sum(r["requirement_score"]["over_claim"] for r in ok),
        "requirements_extract_ms": mean([r["first"].get("requirements_ms") for r in ok if r["first"].get("requirements_ms")]),
        **quality_summary(ok),
    }


def quality_summary(ok: list[dict]) -> dict:
    stars = [r["star_score"] for r in ok if r.get("star_score")]
    quality = [r["question_quality"] for r in ok if r.get("question_quality")]
    return {
        "questions_shown": sum(q["shown"] for q in quality),
        "eligibility_questions": sum(len(q["eligibility_questions"]) for q in quality),
        "already_written_questions": sum(len(q["already_written_questions"]) for q in quality),
        "wasted_answers": sum(len(q["wasted_answers"]) for q in quality),
        "internal_terms": sum(len(q["internal_terms"]) for q in quality),
        "star_items_judged": f'{sum(s["judged"] for s in stars)}/{sum(s["items"] for s in stars)}' if stars else None,
        "star_action_result_agree": f'{sum(s["AR_agree"] for s in stars)}/{sum(s["AR_total"] for s in stars)}' if stars else None,
        "star_situation_task_agree": f'{sum(s["ST_agree"] for s in stars)}/{sum(s["ST_total"] for s in stars)}' if stars else None,
        "star_action_result_over_claim": sum(s["AR_over_claim"] for s in stars) if stars else None,
        "star_action_result_under_claim": sum(s["AR_under_claim"] for s in stars) if stars else None,
    }


def transcript(record: dict) -> str:
    lines = [f"# {record['id']} — {record['company']} {record['title']}", ""]
    if "first" not in record:
        return "\n".join(lines + [f"실패: {record.get('error')}"])
    first = record["first"]
    lines += [f"첫 첨삭 {first['elapsed_ms']}ms · 출력 {first['output_tokens']} 토큰 · 전체 {record['total_s']}초", "",
              "## 요약", first["summary"], "", "## 앱에 보이는 질문 7개"]
    lines += [f"{i + 1}. [{q['kind']}] `{q['field_path']}` {q['question']}" for i, q in enumerate(first["visible"])]
    lines += ["", "## 첫 수정안"]
    for s in first["suggestions"]:
        lines += [f"- `{s['field_path']}` ({s['edit_type']})", f"  - 원문: {s['original']}", f"  - 수정: {s['revision']}"]
    for d in first["dropped"]:
        lines += [f"- 버려짐 `{d['field_path']}` {d['issues']}: {d['original'][:100]}"]
    if first.get("requirement_map"):
        lines += ["", "## 요건 대조", "```json", json.dumps(first["requirement_map"], ensure_ascii=False, indent=1), "```"]
    lines += ["", "## 대화"]
    for i, t in enumerate(record["turns"], 1):
        lines += [f"### {i}. [{t['kind']}] `{t['field_path']}`", f"- 질문: {t['question']}", f"- 답변: {t['answer']}"]
        if "error" in t:
            lines.append(f"- 오류: {t['error']}")
            continue
        lines.append(f"- 재첨삭 {t.get('elapsed_ms')}ms · 답 반영 {t['reflected']}")
        for d in t.get("dropped", []):
            lines.append(f"  - 버려진 수정안 `{d['field_path']}` {d['issues']}")
        for w in t.get("warnings", []):
            lines.append(f"  - 경고: {w}")
        for s in t["suggestions"]:
            lines += [f"  - 수정안 `{s['field_path']}` ({s['edit_type']})", f"    - 원문: {s['original']}", f"    - 수정: {s['revision']}"]
    if record.get("gap_audit"):
        lines += ["", "## 누락 점검", *[f"- {q}" for q in record["gap_audit"]["new_questions"]]]
    fab = record["fabrication"]
    lines += ["", "## 지어낸 흔적", f"- 새 숫자: {fab['new_numbers']}", f"- 새 기술어: {fab['new_terms']}",
              f"- 해 본 적 없는 것 새어 들어감: {fab['not_done_leaks']}"]
    if record["errors"]:
        lines += ["", "## 오류", *[f"- {e}" for e in record["errors"]]]
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--cases", default="dev", help="fixtures/review_cases_<이름>.json")
    parser.add_argument("--label", default="run")
    parser.add_argument("--only", nargs="*", help="이 id의 케이스만")
    parser.add_argument("--max-questions", type=int, default=7, help="앱은 질문을 7개까지 보여준다")
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--apply-polish", action="store_true", help="첫 첨삭의 문장 다듬기를 모두 적용한 뒤 질문에 답한다(앱의 묶음 적용)")
    parser.add_argument("--rescore", help="저장된 실행 폴더의 기록으로 질문 품질 지표만 다시 센다(모델을 부르지 않는다)")
    parser.add_argument("--applicant", choices=["mock", "human"], default="mock",
                        help="human: 짧은 답·줄인 항목 이름·다른 항목 섞기·'안 해 봤어요' 덧붙이기·맞춤법·불확실한 말을 턴마다 한두 개 섞는다")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")

    if args.rescore:
        run = Path(args.rescore)
        saved = json.loads((run / "results.json").read_text(encoding="utf-8"))
        cases = {case["id"]: case for case in load_cases(args.cases)}
        ok = [r for r in saved["records"] if "first" in r and r["id"] in cases]
        for record in ok:
            record["star_score"] = score_star(cases[record["id"]], record["first"].get("star_checks"))
            record["question_quality"] = question_quality(cases[record["id"]], record)
        print(json.dumps({"label": saved["label"], **quality_summary(ok)}, ensure_ascii=False, indent=2))
        for record in ok:
            q = record["question_quality"]
            print(f'- {record["id"]}: 자격 {len(q["eligibility_questions"])} · 이미 적힌 항목 {len(q["already_written_questions"])} '
                  f'· 헛답 {len(q["wasted_answers"])} · 내부 용어 {len(q["internal_terms"])}')
        return

    settings = get_settings()
    cases = load_cases(args.cases)
    if args.only:
        cases = [c for c in cases if c["id"] in set(args.only)]
    applicant = make_applicant(settings, args.applicant)
    out = HERE / "runs" / f"{datetime.now():%Y%m%d-%H%M%S}_{args.label}"
    out.mkdir(parents=True, exist_ok=True)

    def one(case):
        try:
            return run_case(case, settings, applicant, args.max_questions, apply_polish=args.apply_polish)
        except Exception as exc:  # noqa: BLE001
            return {"id": case["id"], "company": case["job"]["company"], "title": case["job"]["title"],
                    "error": f"{type(exc).__name__}: {exc}"[:300], "errors": []}

    if args.workers > 1 and len(cases) > 1:
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            records = list(pool.map(one, cases))
    else:
        records = [one(case) for case in cases]
    summary = aggregate(records)
    (out / "results.json").write_text(json.dumps({"label": args.label, "summary": summary, "records": records},
                                                 ensure_ascii=False, indent=2), encoding="utf-8")
    for record in records:
        (out / f"{record['id']}.md").write_text(transcript(record), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    for record in records:
        if "error" in record:
            print("실패", record["id"], record["error"])
    print("저장:", out)


if __name__ == "__main__":
    main()
