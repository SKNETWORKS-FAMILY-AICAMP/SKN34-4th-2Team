"""Conservative rule candidates from existing article extraction; preview only.

No approval inference, policy writes, LLM execution or operational activation.
Unsupported wording stays unavailable instead of reverting to legacy constants.
"""
from dataclasses import asdict, dataclass
from datetime import date
from decimal import Decimal
import re

from chatbot.calculation_rules import CalculationRules


@dataclass(frozen=True)
class RuleCandidate:
    cohort: str
    document_hash: str
    source_name: str
    article: str
    purpose: str
    denominator: str
    value: str
    evidence: str
    article_text: str
    source_status: str
    review_status: str = 'unverified'

    def metadata(self):
        return asdict(self)


def extract_candidates(rows):
    """Consume complete article records produced by document_records/build_records.

    These deliberately narrow patterns support current formal policy wording.
    Full articles retain qualifications for human review; regex does not certify
    that all semantic exceptions have been interpreted.
    """
    result, seen = [], set()
    patterns = (
        ('completion', 'whole_course', re.compile(r'(\d+(?:\.\d+)?)%\s*이상\)\s*이수하면\s*수료')),
        ('allowance', 'unit_period', re.compile(r'단위기간\s*출석률\s*(\d+(?:\.\d+)?)%\s*이상이면\s*훈련장려금')),
        ('absence_conversion', 'unit_period', re.compile(r'단위기간\s*내\s*지각·조퇴·외출\s*누적\s*(\d+)회는\s*결석\s*1일로\s*환산')),
    )
    for row in rows:
        metadata, text = row['metadata'], row['page_content']
        if metadata.get('structure') != 'article' or metadata.get('kind') != 'policy':
            continue
        cohort, digest = metadata.get('cohort', ''), metadata.get('document_hash', '')
        if not cohort or not re.fullmatch(r'[a-f0-9]{64}', digest):
            raise ValueError('Missing cohort or document fingerprint')
        article = str(metadata.get('article_number', ''))
        if not article:
            raise ValueError('Missing article number')
        identity = (cohort, digest, article)
        if identity in seen:
            raise ValueError('Duplicate article; use whole-article extraction, not search results')
        seen.add(identity)
        for purpose, denominator, pattern in patterns:
            for match in pattern.finditer(text):
                value = Decimal(match[1])
                if not 0 < value <= (100 if purpose != 'absence_conversion' else 10000):
                    raise ValueError('Invalid policy value')
                if purpose == 'completion' and '전체 훈련기간' not in text:
                    continue
                result.append(RuleCandidate(cohort, digest, metadata.get('source_name', ''),
                    article, purpose, denominator, str(value), match[0], text,
                    metadata.get('approval_status', 'unknown')))
    return result


@dataclass(frozen=True)
class PreviewPolicy:
    """Dates supplied explicitly for a scenario; never inferred as approved dates."""
    cohort: str
    document_hash: str
    effective_from: date
    effective_until: date | None
    candidates: tuple[RuleCandidate, ...]

    def __post_init__(self):
        if type(self.effective_from) is not date or (
            self.effective_until is not None and (type(self.effective_until) is not date
                or self.effective_until <= self.effective_from)
        ):
            raise ValueError('Explicit effective dates required; end is exclusive')
        if any(c.cohort != self.cohort or c.document_hash != self.document_hash
               or c.review_status != 'unverified' for c in self.candidates):
            raise ValueError('Mixed cohort/version or unsupported approval status')


def select_candidate(policies, *, cohort, purpose, as_of):
    if type(as_of) is not date:
        raise ValueError('Explicit calculation date required')
    applicable = [p for p in policies if p.cohort == cohort and p.effective_from <= as_of
                  and (p.effective_until is None or as_of < p.effective_until)]
    if len(applicable) != 1:
        raise ValueError('Missing or overlapping policy versions')
    matches = [c for c in applicable[0].candidates if c.purpose == purpose]
    if len(matches) != 1:
        raise ValueError('Missing or conflicting calculation criteria')
    return matches[0]


def preview_threshold(policies, *, cohort, purpose, as_of, recognized, total, denominator):
    if purpose not in ('completion', 'allowance'):
        raise ValueError('Unsupported calculation purpose')
    rule = select_candidate(policies, cohort=cohort, purpose=purpose, as_of=as_of)
    if denominator != rule.denominator:
        raise ValueError('Calculation denominator does not match policy purpose')
    if type(total) is not int or type(recognized) is not int or not 0 <= recognized <= total or total <= 0:
        raise ValueError('Validated positive day counts required')
    return {'is_provisional': True, 'review_status': 'unverified',
        'scenario_date': as_of.isoformat(), 'recognized': recognized, 'total': total,
        'requirement_met': Decimal(recognized)*100 >= Decimal(total)*Decimal(rule.value),
        'rule': rule.metadata(), 'note': '문서 추출 후보에 대한 검토용 계산. 실제 수료·지급 판정 아님.'}


def unit_period_preview_rules(policies, *, cohort, as_of, period_start, period_end, calendar_rules):
    """Bridge to existing unit-period engine, only for explicitly supplied previews.

    Calendar rules are supplied separately. A mid-period revision requires an
    explicit transition rule and is therefore rejected here.
    """
    if not period_start <= as_of <= period_end:
        raise ValueError('Calculation date must be within the selected period')
    selected = []
    for purpose in ('allowance', 'absence_conversion'):
        rule = select_candidate(policies, cohort=cohort, purpose=purpose, as_of=as_of)
        for boundary in (period_start, period_end):
            if select_candidate(policies, cohort=cohort, purpose=purpose, as_of=boundary) != rule:
                raise ValueError('Mid-period policy change requires a transition rule')
        if rule.denominator != 'unit_period':
            raise ValueError('Unit-period basis required')
        selected.append(rule)
    threshold, conversion = selected
    return CalculationRules(version=threshold.document_hash, review_status='unverified',
        source=f'{cohort}: allowance article {threshold.article}; conversion article {conversion.article}; preview only',
        attendance_threshold_percent=float(threshold.value), exceptions_per_absence=int(conversion.value),
        calendar_method=calendar_rules.calendar_method, final_period_method=calendar_rules.final_period_method)
