"""User-confirmed calculation basis; no percentages, records or assistant inference."""
from dataclasses import dataclass
import hashlib
import json
import re

from chatbot.context_cache import redis_client, redis_backoff_active, mark_redis_failure

CLARIFICATION = '이번 단위기간 장려금 기준인가요, 전체 훈련기간 수료 기준인가요?'
TTL_SECONDS = 1800
BASES = {'unit', 'completion', 'both'}
_UNIT = re.compile(r'단위\s*기간|이번\s*(?:달|월)|장려금|훈련\s*수당')
_COMPLETION = re.compile(r'전체\s*(?:과정|훈련(?:\s*기간)?|교육(?:\s*기간)?|기간|출석)|수료|종강까지')
_TOPIC = re.compile(r'출석|출결|지각|조퇴|외출|결석|장려금|수료')
_PERSONAL = re.compile(r'(?<![가-힣])(?:내가|내|나의|저의|제가|나는)(?=\s|출석|출결|지각|결석|장려금|수료)')
_GOAL = re.compile(r'며칠|몇\s*일|얼마|필요|가능|더\s*(?:출석|지각|결석)|넘|달성|현황|상태|어때|괜찮|받을|계산')
_GENERAL = re.compile(r'기준|공식|계산법|규정|조건|자격|마감|신청|정의')
_COMPARE = re.compile(r'둘\s*다|두\s*(?:기준|기간)|각각|비교|모두|함께')
_CHOICE = re.compile(r'모르|헷갈|어느|인지.*인지|인가.*인가')
_SHORT = re.compile(r'^(?:(?:(?:이번)?단위기간|이번달|이번월)(?:장려금|출석)?|장려금|수료(?:기준)?|'
                    r'전체(?:과정|훈련기간|교육기간|기간)(?:수료|출석)?)'
                    r'(?:(?:기준)?(?:으로|로)(?:알려줘|계산해줘|봐줘)?|기준|이요|요|입니다)?$')
_BOTH_SHORT = re.compile(r'^(?:둘다|두기준|두기간)(?:알려줘|비교해줘|요|로)?$')
_CANONICAL = {
    'unit': '내 이번 단위기간의 장려금 출석 기준에서 현재 출석 현황과 추가 정상 출석 필요일을 알려줘.',
    'completion': '내 전체 훈련기간 수료 출석 기준에서 현재 현황과 추가 정상 출석 필요일을 알려줘.',
    'both': '내 단위기간 장려금 기준과 전체 훈련기간 수료 기준의 출석 현황과 추가 정상 출석 필요일을 각각 비교해줘.',
}


@dataclass(frozen=True)
class BasisDecision:
    basis: str | None
    question: str
    needs_clarification: bool = False


def _tail(question):
    return re.split(r'말고|아니라|아니고|아닌|대신', question)[-1].strip()


def is_personal_calculation(question: str) -> bool:
    if not _TOPIC.search(question):
        return False
    core_attendance = re.search(r'출석|출결|지각|조퇴|외출|결석', question)
    if not core_attendance and re.search(r'프로젝트|공지|신청|마감|일정|수료식', question):
        return False
    if re.search(r'(?:다음\s*수업|앞으로|오늘|내일|한\s*번\s*더).*(?:지각|결석|조퇴|외출)'
                 r'.*(?:하면|한다면|할\s*경우|했을\s*때)', question):
        return True
    if _PERSONAL.search(question) and (_GOAL.search(question) or '출석률' in question):
        return True
    if re.search(r'(?:며칠|몇\s*일|더).*출석|출석.*(?:며칠|몇\s*일|더)', question):
        return True
    if re.search(r'며칠|몇\s*일', question) and _TOPIC.search(question):
        return True
    if (_UNIT.search(question) or _COMPLETION.search(question)) and _GOAL.search(question):
        return True
    if '출석률' in question and not _GENERAL.search(question):
        return True
    return bool(re.match(r'\s*(?:그럼|그러면)', question) and _GOAL.search(question))


def resolve_attendance_basis(question: str, previous: dict | None = None) -> BasisDecision:
    """Pure resolver. `previous` is a server selection record, never AI history."""
    previous = previous or {}
    tail = _tail(question)
    compact = re.sub(r'[\s.!?]', '', tail)
    short, both_short = bool(_SHORT.fullmatch(compact)), bool(_BOTH_SHORT.fullmatch(compact))
    selection = bool(previous.get('pending') and (short or both_short))
    if short and (previous.get('basis') in BASES or re.search(r'(?:으로|로)(?:알려줘|계산해줘|봐줘)?$', compact)):
        selection = True
    if both_short and previous.get('basis') in BASES:
        selection = True
    if not is_personal_calculation(question) and not selection:
        return BasisDecision(None, question)
    clauses = re.split(r'그리고|[,;]', question)
    calculation_clauses = [part for part in clauses if is_personal_calculation(part)
        or _SHORT.fullmatch(re.sub(r'[\s.!?]', '', _tail(part)))
        or (_CHOICE.search(part) and (_UNIT.search(part) or _COMPLETION.search(part))
            and not re.search(r'공지|프로젝트|신청|마감|일정', part))]
    scope_text = _tail(' '.join(calculation_clauses)) if len(clauses) > 1 and calculation_clauses else tail
    unit, completion = bool(_UNIT.search(scope_text)), bool(_COMPLETION.search(scope_text))
    if both_short and selection:
        selected = 'both'
    elif unit and completion:
        selected = 'both' if _COMPARE.search(scope_text) and not _CHOICE.search(scope_text) else None
    elif unit:
        selected = 'unit'
    elif completion:
        selected = 'completion'
    else:
        selected = previous.get('basis') if not previous.get('pending') and previous.get('basis') in {'unit', 'completion'} else None
    if selected is None:
        return BasisDecision('clarify', question, True)
    return BasisDecision(selected, _CANONICAL[selected] if selection else question)


def _key(identity: dict) -> str | None:
    fields = [identity.get(key) for key in ('uid', 'cohort', 'thread_id')]
    if not all(isinstance(value, str) and value for value in fields):
        return None
    if fields[2] == 'web' or re.fullmatch(r'[a-f0-9]{24}\.web', fields[2]):
        return None  # Legacy clients cannot distinguish new conversations.
    return 'lms:chat-attendance-basis:v1:' + hashlib.sha256(json.dumps(fields).encode()).hexdigest()


def _read_context(identity: dict) -> dict | None:
    key = _key(identity)
    if key is None or redis_backoff_active():
        return None
    try:
        raw = redis_client().get(key)
    except Exception:
        mark_redis_failure()
        return None
    try:
        value = json.loads(raw) if raw and len(raw) <= 256 else None
        if (isinstance(value, dict) and value.get('version') == 1
                and (value.get('basis') is None or value.get('basis') in BASES)
                and type(value.get('pending')) is bool):
            return value
    except Exception:
        pass
    return None


def _write_context(identity: dict, basis: str | None, pending: bool) -> None:
    key = _key(identity)
    if key is None or redis_backoff_active():
        return
    try:
        redis_client().set(key, json.dumps({'version': 1, 'basis': basis, 'pending': pending}).encode(),
                           ex=TTL_SECONDS)
    except Exception:
        mark_redis_failure()


def resolve_request_basis(question: str, identity: dict) -> BasisDecision:
    tail = re.sub(r'[\s.!?]', '', _tail(question))
    if not is_personal_calculation(question) and not _SHORT.fullmatch(tail) and not _BOTH_SHORT.fullmatch(tail):
        return BasisDecision(None, question)  # Non-attendance requests perform no scope I/O.
    previous = _read_context(identity)
    decision = resolve_attendance_basis(question, previous)
    persist_decision(identity, decision)
    return decision


def persist_decision(identity: dict, decision: BasisDecision) -> None:
    if decision.needs_clarification:
        _write_context(identity, None, True)
    elif decision.basis in BASES:
        _write_context(identity, decision.basis, False)


def prepare_short_basis(question: str, identity: dict) -> BasisDecision:
    """Read-only pre-routing normalization for the limited selection grammar."""
    parts = re.split(r'말고|아니라|아니고|아닌|대신', question)
    labels = [re.sub(r'[\s.!?]', '', part) for part in parts]
    if not all(_SHORT.fullmatch(label) or _BOTH_SHORT.fullmatch(label) for label in labels):
        return BasisDecision(None, question)
    return resolve_attendance_basis(question, _read_context(identity))


def scoped_question(decision: BasisDecision) -> str:
    if decision.basis not in BASES:
        return decision.question
    label = {'unit': '이번 단위기간 장려금', 'completion': '전체 훈련기간 수료',
             'both': '단위기간 장려금과 전체 훈련기간 수료를 각각'}[decision.basis]
    return f'{decision.question}\n[사용자가 확인한 개인 출석 계산 기준: {label}]'
