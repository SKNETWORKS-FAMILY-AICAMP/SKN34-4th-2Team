"""수집 저장소에 남는 채용공고 레코드.

파서가 만드는 `Job`은 "이번에 읽은 공고 한 건"이고, `JobRecord`는 "저장소가
시간에 걸쳐 관리하는 그 공고"다. 언제 처음 봤는지, 마지막으로 확인한 게
언제인지, 몇 번 안 보였는지는 파서가 알 수 없으므로 여기서 관리한다.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from job_matching_bot.schemas.job_posting import Job

# 공고 상태. 더 이상 확인되지 않는다고 즉시 지우지 않고 상태로 남긴다.
STATUS_OPEN = "OPEN"
STATUS_EXPIRED = "EXPIRED"  # 마감일이 지남
STATUS_CLOSED = "CLOSED"  # 소스가 마감이라고 명시
STATUS_REMOVED = "REMOVED"  # 마감일 전인데 소스에서 사라짐

# 소스에서 사라졌다고 바로 REMOVED로 넘기지 않는다. 수집 한 번 실패했다고
# 전체 공고가 삭제 처리되면 안 되기 때문이다.
DEFAULT_MISSING_RUN_LIMIT = 2


@dataclass
class JobRecord:
    """저장소에 보관하는 공고 하나."""

    job: Job
    first_seen_at: str
    last_seen_at: str
    status: str = STATUS_OPEN
    # 연속으로 관측되지 않은 수집 횟수. 다시 보이면 0으로 돌아간다.
    missing_runs: int = 0
    # 내용이 바뀐 횟수. content_hash가 달라질 때만 올라간다.
    revisions: int = 0

    @property
    def key(self) -> tuple[str, str]:
        return (self.job.source, self.job.source_job_id)

    def to_dict(self) -> dict[str, Any]:
        """저장용 평면 딕셔너리. 공고 필드와 생애주기 필드를 함께 담는다."""
        payload = asdict(self.job)
        payload.update(
            {
                "status": self.status,
                "first_seen_at": self.first_seen_at,
                "last_seen_at": self.last_seen_at,
                "missing_runs": self.missing_runs,
                "revisions": self.revisions,
            }
        )
        return payload

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> JobRecord:
        lifecycle = {
            "status": payload.get("status", STATUS_OPEN),
            "first_seen_at": payload["first_seen_at"],
            "last_seen_at": payload["last_seen_at"],
            "missing_runs": payload.get("missing_runs", 0),
            "revisions": payload.get("revisions", 0),
        }
        job_fields = {
            name: payload[name]
            for name in Job.__dataclass_fields__
            if name in payload
        }
        # status는 저장소가 관리하므로 Job 쪽에도 같은 값을 넣어 둔다.
        job_fields["status"] = lifecycle["status"]
        return cls(job=Job(**job_fields), **lifecycle)


@dataclass
class CollectionReport:
    """수집 한 번의 결과. 무엇이 새로 들어오고 무엇이 사라졌는지 남긴다."""

    source: str
    collected_at: str
    new: list[str] = field(default_factory=list)
    updated: list[str] = field(default_factory=list)
    unchanged: list[str] = field(default_factory=list)
    expired: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    # 아직 관측되지 않았지만 실패일 수 있어 상태를 유지한 공고.
    still_missing: list[str] = field(default_factory=list)
    # 목록 페이지에서는 보였지만 상세를 다시 받지 않은 공고. 증분 수집에서
    # 대부분이 여기 들어간다. 내용은 그대로, last_seen_at만 갱신된다.
    observed: list[str] = field(default_factory=list)
    # 필수 필드가 비어 있는 공고. 선택자 오류를 잡기 위한 신호다.
    missing_fields: dict[str, list[str]] = field(default_factory=dict)
    # 파서 버전별 수집 건수.
    parser_versions: dict[str, int] = field(default_factory=dict)

    @property
    def total_collected(self) -> int:
        return len(self.new) + len(self.updated) + len(self.unchanged)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["total_collected"] = self.total_collected
        return payload
