"""Luna supervisor의 명백한 누락만 보정하는 실험용 라우팅 규칙."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from chatbot.student_chatbot import SupervisorDecision


@dataclass(frozen=True)
class RoutingSignals:
    lms: bool = False
    namespaces: tuple[str, ...] = ()
    student_scopes: tuple[str, ...] = ()


_NOTICE = re.compile(
    r"공지|최근\s*안내|운영\s*(?:변경|안내)|휴강|보강|코딩\s*테스트|코테|"
    r"(?:시험|행사|특강|설명회|세미나)\s*(?:일정|날짜|시간|언제)|"
    r"(?:신청|접수)\s*(?:일정|기간|마감|언제)",
    re.IGNORECASE,
)
_PROJECT = re.compile(r"프로젝트|레퍼런스|깃허브|github|포트폴리오|capstone", re.IGNORECASE)
_POLICY_TOPIC = re.compile(
    r"출결|출석|결석|지각|조퇴|외출|공가|장려금|훈련\s*수당|규정|기준|증빙|"
    r"캠퍼스\s*운영|시설\s*(?:이용|사용)|라운지|강의장|음식물|취식|반입"
)
_RULE_INTENT = re.compile(r"어떻게|처리|반영|인정|기준|규정|조건|방법|가능|해야|되나|돼")
_PRIVATE = re.compile(
    r"(?:내|나의|제가|내가|내가\s*낸)\s*(?:출석|출결|결석|지각|조퇴|외출|공가|장려금|"
    r"할\s*일|진도|제출|과제|상담|이력서|마일리지|학습\s*기록)"
)
# 챗봇은 로그인 학생 한 명의 화면에서 실행된다. "이번 달 출결 집계"처럼
# 소유어를 생략해도 개인 수치 자체를 요구하는 표현은 본인 데이터 조회로 본다.
# 반대로 "출결 기준/규정"은 _RULE_INTENT가 정책으로 분류하므로 여기 넣지 않는다.
_IMPLICIT_PERSONAL_ATTENDANCE = re.compile(
    r"(?:이번\s*(?:달|월)|현재|지금|누적)?\s*(?:내\s*)?"
    r"(?:출석률|출결\s*(?:집계|현황|기록)|출석\s*현황)"
)
_CONTENT_CREATION = re.compile(r"대신\s*(?:써|작성)|(?:써|작성|만들어)\s*줘|대필")
_COHORT = re.compile(r"일정|시간표|좌석|게시글|과제|평가|기수\s*정보|링크")
_CURRICULUM_FILE = re.compile(r"커리큘럼\s*(?:파일|pdf)|교육과정\s*(?:파일|pdf)", re.IGNORECASE)
_CURRICULUM_SCHEDULE = re.compile(
    r"(?:이번|다음|오늘|내일|금주|차주|\d{1,2}\s*월)?\s*"
    r"(?:수업|교육|과정|커리큘럼)\s*(?:일정|날짜|기간|언제|뭐|무엇)|"
    r"(?:단위|최종|\d{1,2}\s*차)?\s*프로젝트\s*(?:일정|날짜|기간|언제|시작|종료|마감|발표)|"
    r"(?:이번|다음)\s*주\s*(?:일정|수업|교육|과정)",
    re.IGNORECASE,
)
_MATERIAL_FILE = re.compile(r"강의\s*자료|수업\s*자료|교안")
_RECORD_FILE = re.compile(r"(?:내|나의)\s*(?:학습\s*)?(?:기록|증빙)\s*파일")
_ASSIGNMENT_FILE = re.compile(r"(?:내|나의|내가\s*낸)\s*과제\s*(?:제출\s*)?파일")
_EXPLICIT_PROJECT_COHORT = re.compile(
    r"(?:(?<!\d)\d{1,3}\s*기|cohort[_\s-]*\d{1,3})", re.IGNORECASE,
)
_SESSION_COHORT_NUMBER = re.compile(r"(\d{1,3})")


def detect_routing_signals(question: str) -> RoutingSignals:
    """확실한 표면 신호만 찾는다. 애매한 의미 판정은 Luna에 남긴다."""
    namespaces: list[str] = []
    scopes: list[str] = []
    private_data = (
        bool(_PRIVATE.search(question))
        or bool(_IMPLICIT_PERSONAL_ATTENDANCE.search(question))
    ) and not bool(_CONTENT_CREATION.search(question))
    if _POLICY_TOPIC.search(question) and (not private_data or _RULE_INTENT.search(question)):
        namespaces.append("policy")
    if _NOTICE.search(question):
        namespaces.append("notice")
    if _PROJECT.search(question):
        namespaces.append("project_reference")
    if private_data:
        scopes.append("student_private")
    if _COHORT.search(question) and not private_data:
        scopes.append("cohort_shared")
    if _CURRICULUM_FILE.search(question) or _CURRICULUM_SCHEDULE.search(question):
        scopes.append("curriculum_files")
    if _MATERIAL_FILE.search(question):
        scopes.append("material_files")
    if _RECORD_FILE.search(question):
        scopes.append("record_files")
    if _ASSIGNMENT_FILE.search(question):
        scopes.append("assignment_files")
    return RoutingSignals(
        lms=bool(namespaces or scopes),
        namespaces=tuple(dict.fromkeys(namespaces)),
        student_scopes=tuple(dict.fromkeys(scopes)),
    )


def reconcile_decision(question: str, decision: SupervisorDecision) -> SupervisorDecision:
    """모델 선택을 보존하면서 질문에 명시된 LMS 범위 누락만 합친다.

    Luna가 이미 선택한 범위를 정규식이 제거하면 의미가 생략된 개인 질문과
    복합 질문에서 회귀한다. 허용 목록 검증은 운영 middleware가 담당하므로,
    lab 규칙은 확실한 표면 신호를 추가하는 역할만 한다.
    """
    signals = detect_routing_signals(question)
    if _CONTENT_CREATION.search(question) and not signals.lms:
        return decision.model_copy(update={
            "route": "blocked", "namespaces": [], "student_scopes": [], "query": question,
        })
    if not signals.lms:
        return decision
    namespaces = list(dict.fromkeys([*decision.namespaces, *signals.namespaces]))
    scopes = list(dict.fromkeys([*decision.student_scopes, *signals.student_scopes]))
    return decision.model_copy(update={
        "route": "lms",
        "namespaces": namespaces,
        "student_scopes": scopes,
        "query": decision.query.strip() or question,
    })


def bind_session_cohort_to_project_query(
    query: str, cohort: str, namespaces: list[str],
) -> str:
    """기수를 생략한 프로젝트 질문만 인증된 학생 기수에 묶는다."""
    if "project_reference" not in namespaces or not cohort:
        return query
    if _EXPLICIT_PROJECT_COHORT.search(query):
        return query
    match = _SESSION_COHORT_NUMBER.search(cohort)
    if not match:
        return query
    return f"{query}\n현재 로그인 학생 기수: {match.group(1)}기"


class LabSupervisorGuardrail:
    """운영 middleware 뒤에 lab의 결정론적 보정을 적용한다."""

    def __init__(self, base: Any) -> None:
        self._base = base

    def invoke(self, inputs: dict[str, Any], handler: Any) -> SupervisorDecision:
        decision = self._base.invoke(inputs, handler)
        tasks = list(getattr(decision, "tasks", []) or [])
        if tasks:
            task_namespaces = [
                namespace
                for task in tasks
                for namespace in getattr(task, "namespaces", [])
            ]
            task_scopes = [
                scope
                for task in tasks
                for scope in getattr(task, "student_scopes", [])
            ]
            task_queries = [
                str(getattr(task, "query", "")).strip()
                for task in tasks
                if str(getattr(task, "query", "")).strip()
            ]
            decision = decision.model_copy(update={
                "namespaces": list(dict.fromkeys([
                    *decision.namespaces, *task_namespaces,
                ])),
                "student_scopes": list(dict.fromkeys([
                    *decision.student_scopes, *task_scopes,
                ])),
                # 현재 그래프는 namespace마다 하나의 검색어를 받는다. 하위 요청을
                # 모두 포함시켜 한 요청이 검색어에서 사라지지 않게 한다.
                "query": "\n".join(dict.fromkeys(task_queries)) or decision.query,
            })
        messages = inputs.get("messages") or []
        question = str(getattr(messages[-1], "content", "")) if messages else ""
        return reconcile_decision(question, decision)
