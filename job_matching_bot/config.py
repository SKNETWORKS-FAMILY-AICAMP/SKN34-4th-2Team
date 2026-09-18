"""전역 설정: 지금 시각과 기본 입출력 경로.

경로는 패키지 위치를 기준으로 계산하므로 어느 디렉터리에서 실행해도 동작한다.
"""

from datetime import datetime, timedelta, timezone
from pathlib import Path

KST = timezone(timedelta(hours=9))

# 테스트가 시계를 고정할 때만 채운다(`tests/__init__.py`). 운영에서는 늘 None이다.
_frozen_now: datetime | None = None


def now() -> datetime:
    """마감 판정·수집 시각의 기준. **운영은 지금, 테스트는 고정한 시각.**

    예전에는 POC 때 고정한 `AS_OF`(2026-09-02 12:00)가 운영 함수 7곳의 기본값이었다.
    시각을 안 넘기고 부르면 9월 2일 기준으로 마감을 판정했고, 실제로 만료·삭제된 공고를
    열린 것으로 되돌린 적이 있다(`sqlite_store.refresh`).
    """
    return _frozen_now or datetime.now(KST)


def freeze_now(at: datetime | None) -> None:
    """테스트 전용. None을 주면 풀린다."""
    global _frozen_now
    _frozen_now = at


PACKAGE_ROOT = Path(__file__).resolve().parent
REPO_ROOT = PACKAGE_ROOT.parent

FIXTURES_DIR = PACKAGE_ROOT / "fixtures"
ARTIFACTS_DIR = PACKAGE_ROOT / "artifacts"

# 크롤러 출력. 상세는 한 건씩 이어 쓰는 JSON Lines, 목록은 JSON 배열.
RAW_DIR = ARTIFACTS_DIR / "raw"
DEFAULT_SARAMIN_INPUT = RAW_DIR / "saramin_detail.jsonl"
DEFAULT_SARAMIN_LIST = RAW_DIR / "saramin_raw.json"
# 웹용 가상 이력서. 시드 스크립트와 앱의 "목업 채우기" 메뉴가 같은 원본을 쓴다.
DEFAULT_RESUME_MOCKS_INPUT = REPO_ROOT / "scripts" / "resume_mocks.json"
DEFAULT_RESUME_MOCKS_DART_OUTPUT = (
    REPO_ROOT / "lib" / "features" / "resume" / "ai_coach" / "data" / "generated" / "resume_mocks.g.dart"
)
