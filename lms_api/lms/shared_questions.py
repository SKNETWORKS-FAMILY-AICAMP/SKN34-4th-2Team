"""공고 맞춤 지원 · 자소서 문항 공유 — 같은 회사 · 시즌 · 직무를 고른 수강생끼리 정리한 문항을 나눠 쓴다.

저장은 첨삭 v2 의 recruit_roles(0014)를 쓴다. 한 줄이 「회사 + 시즌 + 직무 + 문항 목록」 한 벌이다.

- 공유: source_type 'company_site' 는 모두에게(반려 · 이상해요 2명은 숨김), 'other' 는 올린 학생만.
  첨삭 v2 의 shared_roles(확인된 것만)와 달리 확인 절차 없이 바로 보인다(2026-10-08 사용자 결정).
- 회사 · 시즌은 고른 공고에서 정한다. 회사는 company_profiles(canonical_company_key), 시즌은 공채 카드와 같은 season_of.
- 직무는 학생이 고른다. 띄어쓰기 · 꼬리말(직무 · 분야 …) · 줄임말만 다른 이름은 role_key 로 한 직무가 된다.
  그 밖에 이름은 달라도 문항이 같으면 확정할 때 묻고(check), 보여 줄 때도 문항이 같은 정리는 한 장으로 합친다.
- 「모든 직무 공통」은 직무 이름 COMMON_ROLE 로 두고 어느 직무를 골라도 함께 보여 준다.
- 사용 수는 「이 문항으로 쓰기」를 누를 때 올린다. 올린 학생 자신은 세지 않는다.
- 이상해요는 recruit_role_reports(팀원 migration 대기)가 있을 때만 받는다. 없으면 버튼을 숨긴다.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any

from django.db import connection, transaction
from django.db.models import F, Q

from . import featured_postings
from .models import CompanyProfiles, RecruitRoles
from .recruit_role_store import canonical_company_key, content_hash, submit_role, validate_content

COMMON_ROLE = "모든 직무 공통"
REPORTS_TO_HIDE = 2
REPORT_REASONS = ("other_company", "wrong", "past_season")
MAX_QUESTIONS = 20
# recruit_roles.role_description 은 비울 수 없다. 내용 지문(content_hash)에 들어가 늘 같은 글로 둔다
DESCRIPTION = "수강생이 공고 맞춤 지원에서 정리한 자기소개서 문항"

# 직무 이름을 한 직무로 접는 규칙. 확신이 있는 것만 — 잘못 묶으면 다른 직무 문항이 섞인다.
# AI 계열 별칭은 코치에게 묻기의 job_matching_bot/matching/role_normalize.py 와 같다(Django 이미지엔 그 패키지가 없어 옮김)
_ROLE_ALIASES = {
    "ai개발자": "ai개발", "ai엔지니어": "ai개발", "aiengineer": "ai개발", "aideveloper": "ai개발",
    "인공지능개발자": "ai개발", "인공지능엔지니어": "ai개발", "인공지능개발": "ai개발",
}
_ROLE_WORDS = (("소프트웨어", "sw"), ("software", "sw"), ("개발자", "개발"))
_ROLE_SUFFIX = re.compile(r"(직무|분야|직군|부문|담당|파트|포지션)$")
_PUNCT = re.compile(r"[\s·・,./()\[\]{}<>\-_&+|:;'\"]+")

# 문항 비교 — 앞 번호 · 글자 수 표기 · 띄어쓰기 · 문장부호만 다르면 같은 문항
_NUMBER = re.compile(r"^\s*(\d{1,2}\s*[.)\-]|[①-⑳]|Q\s*\d{1,2}\s*[.)]?|[가-하]\s*[.)])\s*")
_LIMIT_NOTE = re.compile(r"[\[(][^\])]*\d[\d,]*\s*자[^\])]*[\])]")


class SharedQuestionError(Exception):
    def __init__(self, status: int, detail: str) -> None:
        super().__init__(detail)
        self.status = status
        self.detail = detail


def role_key(name: str) -> str:
    text = unicodedata.normalize("NFKC", name or "").casefold()
    text = _PUNCT.sub("", text)
    for word, short in _ROLE_WORDS:
        text = text.replace(word, short)
    while len(text) > 2 and _ROLE_SUFFIX.search(text):
        text = _ROLE_SUFFIX.sub("", text)
    return _ROLE_ALIASES.get(text, text)


def question_key(text: str) -> str:
    text = unicodedata.normalize("NFKC", text or "")
    text = _LIMIT_NOTE.sub("", _NUMBER.sub("", text))
    return re.sub(r"[\W_]+", "", text).casefold()


def questions_key(questions: list[dict[str, Any]]) -> frozenset[str]:
    return frozenset(k for k in (question_key(q.get("text") or "") for q in questions) if k)


def clean_questions(raw: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """화면의 [{question, limit}] → recruit_roles 의 [{order, text, character_limit}]. 빈 문항은 뺀다."""
    out = []
    for item in raw[:MAX_QUESTIONS]:
        text = " ".join(str(item.get("question") or "").split())[:500]
        if not text:
            continue
        row: dict[str, Any] = {"order": len(out) + 1, "text": text}
        limit = item.get("limit")
        if isinstance(limit, int) and 1 <= limit <= 10000:
            row["character_limit"] = limit
        out.append(row)
    return out


def posting_context(job_id: str) -> dict[str, Any]:
    with connection.cursor() as cur:
        cur.execute("SELECT company, title, posted_at, deadline FROM jobs.jobs WHERE job_id = %s", [job_id])
        row = cur.fetchone()
    if row is None or not (row[0] or "").strip():
        raise SharedQuestionError(404, "공고를 찾을 수 없어요.")
    company, title, posted_at, deadline = row
    return {
        "company": company.strip(),
        "companyKey": canonical_company_key(company),
        "season": featured_postings.season_of(title or "", posted_at, deadline),
        "title": title or "",
    }


def _reports_table() -> bool:
    with connection.cursor() as cur:
        cur.execute("SELECT to_regclass('public.recruit_role_reports') IS NOT NULL")
        return bool(cur.fetchone()[0])


def _hidden_ids(role_ids: list[Any]) -> set[str]:
    if not role_ids or not _reports_table():
        return set()
    with connection.cursor() as cur:
        cur.execute(
            """SELECT role_id::text FROM recruit_role_reports WHERE role_id = ANY(%s::uuid[])
               GROUP BY role_id HAVING count(DISTINCT user_id) >= %s""",
            [[str(i) for i in role_ids], REPORTS_TO_HIDE],
        )
        return {r[0] for r in cur.fetchall()}


def _visible_roles(user_id: int, company_key: str, season: str) -> list[RecruitRoles]:
    rows = list(
        RecruitRoles.objects.filter(company__company_key=company_key, season=season)
        .filter(Q(source_type="company_site") & ~Q(verification_status="rejected") | Q(created_by_id=user_id))
        .order_by("-use_count", "created_at")
    )
    hidden = _hidden_ids([r.pk for r in rows])
    return [r for r in rows if str(r.pk) not in hidden or r.created_by_id == user_id]


def _set_view(rows: list[RecruitRoles], user_id: int) -> dict[str, Any]:
    """문항이 같은 정리 여러 줄 → 화면의 한 장. 문항은 가장 많이 쓴 줄 것을 보여 준다."""
    top = rows[0]
    return {
        "id": str(top.pk),
        "ids": [str(r.pk) for r in rows],
        "roleNames": list(dict.fromkeys(r.role_name for r in rows)),
        "questions": [{"question": q["text"], "limit": q.get("character_limit")} for q in top.questions],
        "useCount": sum(r.use_count for r in rows),
        "updatedAt": max(r.updated_at for r in rows).isoformat(),
        "mine": any(r.created_by_id == user_id for r in rows),
        "shared": any(r.source_type == "company_site" for r in rows),
    }


def _merge_sets(rows: list[RecruitRoles], user_id: int) -> list[dict[str, Any]]:
    groups: dict[frozenset[str], list[RecruitRoles]] = {}
    for row in rows:
        groups.setdefault(questions_key(row.questions), []).append(row)
    sets = [_set_view(group, user_id) for group in groups.values()]
    return sorted(sets, key=lambda s: (-s["useCount"], s["updatedAt"]))


def list_shared(user_id: int, job_id: str) -> dict[str, Any]:
    """고른 공고의 회사 · 시즌에 정리된 문항 — 직무별로 묶고, 공통 문항은 따로."""
    context = posting_context(job_id)
    rows = _visible_roles(user_id, context["companyKey"], context["season"])
    by_role: dict[str, list[RecruitRoles]] = {}
    common: list[RecruitRoles] = []
    for row in rows:
        if row.role_name == COMMON_ROLE:
            common.append(row)
        else:
            by_role.setdefault(role_key(row.role_name), []).append(row)
    roles = []
    for key, group in by_role.items():
        sets = _merge_sets(group, user_id)
        names = list(dict.fromkeys(r.role_name for r in sorted(group, key=lambda r: -r.use_count)))
        roles.append({"key": key, "name": names[0], "names": names, "sets": sets,
                      "useCount": sum(s["useCount"] for s in sets), "people": len({r.created_by_id for r in group})})
    roles.sort(key=lambda r: (-r["useCount"], -r["people"], r["name"]))
    return {**context, "roles": roles, "common": _merge_sets(common, user_id), "canReport": _reports_table()}


def _role_names(company_key: str, season: str) -> dict[str, str]:
    """이 회사 · 시즌에 이미 있는 직무 — role_key → 가장 많이 쓴 이름"""
    names: dict[str, str] = {}
    for name in (RecruitRoles.objects.filter(company__company_key=company_key, season=season)
                 .exclude(role_name=COMMON_ROLE).order_by("-use_count").values_list("role_name", flat=True)):
        names.setdefault(role_key(name), name)
    return names


def check(user_id: int, job_id: str, role_name: str, raw_questions: list[dict[str, Any]]) -> dict[str, Any]:
    """확정 전 — 다른 이름 직무에 문항이 같은 정리가 있으면 알려 준다(합칠지 묻는다)."""
    context = posting_context(job_id)
    questions = clean_questions(raw_questions)
    mine = questions_key(questions)
    key = role_key(role_name)
    if not mine or role_name == COMMON_ROLE:
        return {"sameRole": None}
    for row in _visible_roles(user_id, context["companyKey"], context["season"]):
        if row.role_name != COMMON_ROLE and role_key(row.role_name) != key and questions_key(row.questions) == mine:
            return {"sameRole": {"name": row.role_name, "useCount": row.use_count}}
    return {"sameRole": None}


def _company(context: dict[str, Any]) -> CompanyProfiles:
    row, _ = CompanyProfiles.objects.get_or_create(
        company_key=context["companyKey"], defaults={"company_name": context["company"][:255]},
    )
    return row


def save(user_id: int, job_id: str, role_name: str, raw_questions: list[dict[str, Any]], *, share: bool) -> dict[str, Any]:
    """학생이 문항을 확정했을 때. 같은 직무에 문항이 같은 정리가 있으면 새로 만들지 않고 그 정리를 쓴 것으로 센다."""
    context = posting_context(job_id)
    questions = clean_questions(raw_questions)
    name = " ".join((role_name or "").split())[:255]
    if not questions or not name:
        raise SharedQuestionError(400, "직무와 문항을 정해 주세요.")
    # 띄어쓰기 · 꼬리말만 다른 이름은 이미 있는 이름으로 — 칩이 갈라지지 않게
    if name != COMMON_ROLE:
        name = _role_names(context["companyKey"], context["season"]).get(role_key(name), name)
    mine = questions_key(questions)
    for row in _visible_roles(user_id, context["companyKey"], context["season"]):
        same_role = row.role_name == name or (name != COMMON_ROLE and row.role_name != COMMON_ROLE
                                              and role_key(row.role_name) == role_key(name))
        if same_role and questions_key(row.questions) == mine and (row.source_type == "company_site" or row.created_by_id == user_id):
            use(user_id, str(row.pk))
            return {"id": str(row.pk), "created": False, "roleName": row.role_name}
    source_type = "company_site" if share else "other"
    try:
        with transaction.atomic():
            row = submit_role(
                user_id=user_id, company_id=_company(context).pk, season=context["season"], role_name=name,
                role_description=DESCRIPTION, questions=questions, source_type=source_type, job_id=job_id,
            )
    except RecruitRoles.DoesNotExist:
        # 같은 문항을 다른 학생이 방금 올렸다 — submit_role 은 확인 전 남의 정리를 열지 않는다. 우리 공유 규칙으로는 보이는 정리다
        requirements, normalized = validate_content(DESCRIPTION, {}, questions)
        row = RecruitRoles.objects.get(company__company_key=context["companyKey"], season=context["season"], role_name=name,
                                       source_type="company_site", content_hash=content_hash(DESCRIPTION, requirements, normalized))
        use(user_id, str(row.pk))
        return {"id": str(row.pk), "created": False, "roleName": row.role_name}
    return {"id": str(row.pk), "created": True, "roleName": row.role_name}


def use(user_id: int, role_id: str) -> None:
    """「이 문항으로 쓰기」 — 볼 수 있는 정리만, 올린 학생 자신은 세지 않는다."""
    row = RecruitRoles.objects.filter(pk=role_id).filter(Q(source_type="company_site") | Q(created_by_id=user_id)).first()
    if row is None:
        raise SharedQuestionError(404, "정리를 찾을 수 없어요.")
    if row.created_by_id != user_id:
        RecruitRoles.objects.filter(pk=row.pk).update(use_count=F("use_count") + 1)


def report(user_id: int, role_id: str, reason: str) -> dict[str, Any]:
    if reason not in REPORT_REASONS:
        raise SharedQuestionError(400, "이유를 골라 주세요.")
    if not _reports_table():
        raise SharedQuestionError(503, "아직 이상해요를 받을 수 없어요.")
    if not RecruitRoles.objects.filter(pk=role_id, source_type="company_site").exists():
        raise SharedQuestionError(404, "정리를 찾을 수 없어요.")
    with connection.cursor() as cur:
        cur.execute(
            """INSERT INTO recruit_role_reports (role_id, user_id, reason, created_at) VALUES (%s, %s, %s, now())
               ON CONFLICT (role_id, user_id) DO NOTHING""",
            [role_id, user_id, reason],
        )
    return {"hidden": str(role_id) in _hidden_ids([role_id])}
