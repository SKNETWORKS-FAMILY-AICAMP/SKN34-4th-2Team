"""Conservative, pure answer-effort selection from existing server context."""
from dataclasses import dataclass
from datetime import date
import math
import re

from chatbot.active_policy_rules import validated_calendar_basis
from chatbot.attendance_basis import resolve_attendance_basis

EFFORT_REASONS = frozenset({
    'simple_unit', 'simple_completion', 'simple_schedule', 'policy_interpretation',
    'comparison', 'compound_request', 'unknown_basis', 'data_unavailable',
    'insufficient_calculation', 'other_request', 'fixed_setting', 'default_setting', 'no_model_call',
})


@dataclass(frozen=True)
class EffortDecision:
    effort: str
    reason: str


def _number(value):
    return (type(value) is int and value >= 0) or (type(value) is float and math.isfinite(value) and value >= 0)


def _matches_target(question, threshold):
    targets = re.findall(r'(\d+(?:\.\d+)?)\s*%', question)
    if not targets:
        return True
    try:
        expected = float(threshold) if type(threshold) in (str, int, float) else float('nan')
        return math.isfinite(expected) and expected >= 0 and all(float(value) == expected for value in targets)
    except (TypeError, ValueError, OverflowError):
        return False


def _issue(value):
    if isinstance(value, dict):
        if value.get('errors') or value.get('unavailable_reason') or value.get('calendar_unavailable_reason'):
            return True
        if value.get('status') in ('unavailable', 'conflicting', 'contradicted', 'uncertain'):
            return True
        return any(_issue(item) for item in value.values())
    if isinstance(value, list):
        return any(_issue(item) for item in value)
    return False


def _calendar_ready(context, cohort):
    if not isinstance(context, dict) or context.get('schedule_status') != 'generated_unconfirmed':
        return False
    try:
        start = date.fromisoformat(context['course_start_date'])
        end = date.fromisoformat(context['course_end_date'])
        if end < start:
            return False
        snapshot = context['policy_calculation']
        basis = validated_calendar_basis(snapshot)
        if cohort and snapshot['cohort'] != cohort:
            return False
        return basis == context.get('calendar_basis')
    except (KeyError, TypeError, ValueError):
        return False


def _personal_context(state):
    student = state.get('student_context') or {}
    data = (student.get('data') or {}) if isinstance(student, dict) else {}
    if not isinstance(data, dict):
        return None
    contexts = [data[scope].get('unit_period_context') for scope in ('student_attendance', 'student_private')
                if isinstance(data.get(scope), dict) and isinstance(data[scope].get('unit_period_context'), dict)]
    if not contexts:
        return None
    # Different representations may omit record details, but calculation values
    # must agree. Do not merge them to make a low-effort case appear complete.
    keys = ('calculation_rules', 'calendar_basis', 'periods', 'completion_progress')
    if any(any(context.get(key) != contexts[0].get(key) for key in keys) for context in contexts[1:]):
        return None
    return contexts[0]


def choose_answer_effort(state: dict, *, basis: str | None = None) -> EffortDecision:
    """No model calls, source mutation, namespace shortcuts or data filtering."""
    medium = lambda reason: EffortDecision('medium', reason)
    question = state.get('question', '')
    if len(state.get('tasks') or []) > 1 or len(re.findall(r'[?？]', question)) > 1 \
            or re.search(r'그리고|동시에|한\s*번에|추가로|그\s*다음|'
                r'(?:지각|결석|조퇴|외출).*(?:하고|뒤|후|다음).*(?:지각|결석|조퇴|외출)', question):
        return medium('compound_request')
    basis = basis or state.get('attendance_basis') or resolve_attendance_basis(question).basis
    if basis == 'both' or re.search(r'비교|차이|둘\s*다|각각|어느\s*(?:기준|쪽)', question):
        return medium('comparison')
    if re.search(r'정책|규정|공식|예외|조건|증빙|공가|자격|환급|해석|충돌|특례|신청|'
                 r'정정|수정|변경|가정|바꾸|바뀌|취소|재계산|과거|어제|지난|왜|근거|이유|어떻게\s*계산', question):
        return medium('policy_interpretation')
    if re.search(r'\d+(?:\.\d+)?\s*%\s*(?:라면|면|로)', question):
        return medium('policy_interpretation')
    student = state.get('student_context') or {}
    scopes = set(state.get('student_scopes') or (student.get('requested_scopes') if isinstance(student, dict) else []) or [])
    if scopes - {'student_attendance', 'cohort_shared'}:
        return medium('compound_request')
    if _issue(state.get('student_context', {})) or _issue(state.get('unit_period_context', {})):
        return medium('data_unavailable')
    for document in state.get('documents') or []:
        metadata = document.metadata
        if metadata.get('context_truncated') or metadata.get('unresolved_article_refs'):
            return medium('data_unavailable')
    cohort = state.get('cohort')
    if basis in ('unit', 'completion'):
        if scopes - {'student_attendance'}:
            return medium('compound_request')
        if not re.search(r'출석률|출석\s*(?:현황|상태|어때|확인)|(?:며칠|몇\s*일|얼마).*(?:더|필요|출석)|'
                         r'(?:추가|정상|더).*출석|출석.*(?:필요|며칠|몇\s*일|어때)|'
                         r'(?:지각|결석|조퇴|외출).*(?:하면|한다면)|수료.*(?:가능|현황|어때)', question):
            return medium('other_request')
        context = _personal_context(state)
        if not _calendar_ready(context, cohort):
            return medium('data_unavailable')
        if basis == 'completion':
            # Whole-course progress is not a precomputed future-status scenario.
            if re.search(r'지각|결석|조퇴|외출', question) and re.search(r'하면|한다면|할\s*경우|했을\s*때', question):
                return medium('insufficient_calculation')
            progress = context.get('completion_progress') or {}
            rule = progress.get('rule') or {}
            if not _matches_target(question, progress.get('threshold_percent')):
                return medium('policy_interpretation')
            if (progress.get('unavailable_reason') or progress.get('purpose') != 'completion'
                    or rule.get('document_hash') != context['calendar_basis']['document_hash']
                    or not all(_number(progress.get(key)) for key in (
                        'scheduled_days', 'recorded_days', 'recognized_attendance_days',
                        'required_recognized_days', 'additional_normal_attendance_days_needed'))
                    or progress.get('unrecorded_past_or_today_days') != 0):
                return medium('insufficient_calculation')
            return EffortDecision('low', 'simple_completion')
        rules = context.get('calculation_rules') or {}
        if not _matches_target(question, rules.get('attendance_threshold_percent')):
            return medium('policy_interpretation')
        if context.get('calculation_unavailable_reason') or rules.get('version') != context['calendar_basis']['document_hash']:
            return medium('insufficient_calculation')
        current = context.get('current_unit_period')
        period = next((row for row in context.get('periods', []) if row.get('number') == current), {})
        estimate = period.get('in_progress_estimate') or {}
        if (type(current) is not int or estimate.get('projection_status') != 'conditional_estimate'
                or not all(_number(estimate.get(key)) for key in (
                    'recorded_scheduled_days', 'recognized_attendance_days', 'attendance_rate',
                    'full_period_required_recognized_days', 'additional_normal_attendance_days_needed'))
                or any(period.get(key) != 0 for key in ('unrecorded_past_days', 'unrecorded_today_days', 'future_recorded_days'))):
            return medium('insufficient_calculation')
        if re.search(r'지각|결석|조퇴|외출', question) and re.search(r'하면|한다면|할\s*경우|했을\s*때', question):
            if (not re.search(r'(?<![가-힣])다음\s*(?:수업|미기록\s*미래\s*수업일)', question)
                    or re.search(r'오늘|내일|모레|특정|\d+\s*(?:월|일)|다다음', question)):
                return medium('insufficient_calculation')
            status = next((status for text, status in (('지각', 'late'), ('결석', 'absent'),
                ('조퇴', 'earlyLeave'), ('외출', 'outing')) if text in question), None)
            scenario = estimate.get('next_scheduled_day_scenarios', {}).get(status, {})
            if (not _number(scenario.get('additional_normal_attendance_days_needed'))
                    or type(scenario.get('reachable_with_future_normal_attendance')) is not bool):
                return medium('insufficient_calculation')
        return EffortDecision('low', 'simple_unit')
    if basis == 'clarify' or re.search(r'출석률|며칠.*출석|출석.*며칠', question):
        return medium('unknown_basis')
    if re.search(r'개강|종강|단위\s*기간|훈련\s*기간', question) \
            and re.search(r'언제|날짜|시작|종료|일정|기간', question):
        context = state.get('unit_period_context', {})
        if not _calendar_ready(context, cohort):
            return medium('data_unavailable')
        if '단위' in question:
            current = context.get('current_unit_period')
            period = next((row for row in context.get('periods', []) if row.get('number') == current), None)
            if type(current) is not int or period is None:
                return medium('data_unavailable')
            try:
                period_start = date.fromisoformat(period['start_date'])
                period_end = date.fromisoformat(period['end_date'])
                if not date.fromisoformat(context['course_start_date']) <= period_start <= period_end <= date.fromisoformat(context['course_end_date']):
                    return medium('data_unavailable')
            except (KeyError, TypeError, ValueError):
                return medium('data_unavailable')
        return EffortDecision('low', 'simple_schedule')
    return medium('other_request')
