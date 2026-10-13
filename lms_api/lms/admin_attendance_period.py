"""관리자 통계에도 학생 챗봇의 활성 정책과 단위기간 계산을 사용한다."""
from pathlib import Path
import sys

_repo_root = str(Path(__file__).resolve().parents[2])
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)

from chatbot.active_policy_rules import load_active_snapshot, validated_calendar_basis
from chatbot.unit_period import calculate_unit_period_context


class _MappingCursor:
    """Shared policy reader expects psycopg mapping rows and execute chaining."""
    def __init__(self, cursor):
        self.cursor = cursor

    def execute(self, sql, params):
        self.cursor.execute(sql, params)
        return self

    def fetchone(self):
        row = self.cursor.fetchone()
        return dict(zip((column[0] for column in self.cursor.description), row)) if row else None


def attendance_unit_period(cur, cohort, today, previous=False):
    cur.execute("SELECT start_date, end_date FROM cohorts WHERE id = %s", [cohort["id"]])
    dates = cur.fetchone()
    if not dates or not all(dates):
        raise ValueError("기수의 개강일 또는 종강일이 없어 단위기간을 확인할 수 없습니다.")
    try:
        snapshot = load_active_snapshot(_MappingCursor(cur), cohort["code"])
        basis = validated_calendar_basis(snapshot)
    except Exception as exc:
        raise ValueError("활성 기수 정책에서 단위기간 기준을 확인하지 못했습니다. 기수 정책을 확인해 주세요.") from exc
    context = calculate_unit_period_context(*dates, today=today, require_policy=True,
        calendar_basis=basis, cohort=cohort["code"])
    if context.get("calendar_unavailable_reason"):
        raise ValueError(context["calendar_unavailable_reason"])
    number = context["current_unit_period"]
    if number is None:
        raise ValueError("현재 진행 중인 단위기간이 없습니다. 조회할 날짜 범위를 지정해 주세요.")
    number -= int(previous)
    period = next((p for p in context["periods"] if p["number"] == number), None)
    if period is None:
        raise ValueError("이 기수의 이전 단위기간이 없습니다.")
    return {
        "number": number, "start": period["start_date"], "end": period["end_date"],
        "asOf": today.isoformat(), "isProvisional": context["is_provisional"],
        "policySource": snapshot.get("storage_key"),
    }
