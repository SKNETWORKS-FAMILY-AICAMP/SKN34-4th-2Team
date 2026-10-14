"""Server-owned calculation assumptions, separate from the calculation algorithms.

The bundled configuration preserves legacy estimates, not approved policy.
Never populate this object from a student request or an LLM response.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from decimal import Decimal, ROUND_CEILING
from pathlib import Path
import re


def calendar_method_from_basis(basis: dict | None, *, cohort: str | None = None,
                               document_hash: str | None = None) -> str:
    """Validate server-extracted provenance before choosing a calendar method."""
    expected = {
        'status': 'extracted', 'anchor': 'course_start', 'cycle': 'calendar_month',
        'end': 'next_start_minus_one_day', 'last_period': 'course_end',
        'class_days': 'cohort_schedule', 'month_end_handling': 'unspecified',
    }
    if not isinstance(basis, dict) or any(basis.get(k) != v for k, v in expected.items()):
        raise ValueError('활성 정책의 단위기간 산정 기준 미확인 또는 충돌')
    digest = basis.get('document_hash')
    if (not isinstance(digest, str) or not re.fullmatch(r'[a-f0-9]{64}', digest)
            or not isinstance(basis.get('cohort'), str) or not basis['cohort']
            or not basis.get('article') or not basis.get('evidence')):
        raise ValueError('단위기간 산정 기준의 원문 출처 미확인')
    if ((cohort is not None and basis['cohort'] != cohort)
            or (document_hash is not None and digest != document_hash)):
        raise ValueError('단위기간 산정 기준의 기수 또는 정책 버전 불일치')
    return 'anchored_month_strict'


@dataclass(frozen=True)
class CalculationRules:
    version: str
    review_status: str
    source: str
    attendance_threshold_percent: float
    exceptions_per_absence: int
    calendar_method: str
    final_period_method: str

    def __post_init__(self):
        if not self.version or not self.source:
            raise ValueError("Calculation rule provenance is required")
        # Approval and cohort applicability are not implemented in this first step.
        if self.review_status != "unverified":
            raise ValueError("Only unverified calculation assumptions are supported")
        threshold = self.attendance_threshold_percent
        if isinstance(threshold, bool) or not isinstance(threshold, (int, float)) or not 0 < threshold <= 100:
            raise ValueError("Attendance threshold must be between 0 and 100")
        if type(self.exceptions_per_absence) is not int or self.exceptions_per_absence < 1:
            raise ValueError("Exception conversion count must be a positive integer")
        if (self.calendar_method not in {"anchored_month_clamped", "anchored_month_strict"}
                or self.final_period_method != "clip_to_course_end"):
            raise ValueError("Unsupported calendar calculation method")

    def metadata(self) -> dict:
        return asdict(self)

    def requirement_met(self, recognized: int, total: int) -> bool | None:
        if total <= 0:
            return None
        return Decimal(recognized) * 100 >= Decimal(total) * Decimal(str(self.attendance_threshold_percent))

    def required_days(self, total: int) -> int:
        value = Decimal(total) * Decimal(str(self.attendance_threshold_percent)) / 100
        return int(value.to_integral_value(rounding=ROUND_CEILING))


def load_calculation_rules() -> CalculationRules:
    # No default fallback: a missing/invalid configuration must stop the estimate.
    data = json.loads(Path(__file__).with_name("calculation_rules.json").read_text(encoding="utf-8"))
    return CalculationRules(**data)
