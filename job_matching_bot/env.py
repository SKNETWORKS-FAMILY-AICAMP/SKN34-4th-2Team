"""`.env` 파일에서 환경변수를 읽는다.

로컬 개발의 단일 원본은 레포 루트 `.env`다. Firebase Functions 배포 시에는
`scripts/sync-functions-env.ps1`가 이 파일을 `functions/.env`로 복사한다.

외부 패키지(python-dotenv)를 쓰지 않는다. 이 패키지는 표준 라이브러리만으로
동작하는 것이 원칙이고, 필요한 문법이 `KEY=VALUE` 몇 줄뿐이라서다.

**이미 설정된 환경변수를 덮어쓰지 않는다.** 셸에서 넘긴 값이 파일보다 우선이어야
CI나 일회성 실행에서 값을 바꿔 끼울 수 있다.
"""

from __future__ import annotations

import os
from pathlib import Path

from job_matching_bot.config import REPO_ROOT

DEFAULT_ENV_PATH = REPO_ROOT / ".env"

_loaded = False


def parse_env(text: str) -> dict[str, str]:
    """`.env` 텍스트를 딕셔너리로 만든다.

    주석(`#`)과 빈 줄은 건너뛰고, `export ` 접두사와 값을 감싼 따옴표는 벗긴다.
    """
    values: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export ") :]
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if key:
            values[key] = value
    return values


def load_env(path: Path | None = None, override: bool = False) -> list[str]:
    """`.env`를 읽어 `os.environ`에 채운다. 채워진 키 이름을 돌려준다.

    값은 절대 로그로 남기지 않는다. 키 이름만 반환한다.
    """
    env_path = Path(path) if path else DEFAULT_ENV_PATH
    if not env_path.exists():
        return []

    applied = []
    for key, value in parse_env(env_path.read_text(encoding="utf-8", errors="replace")).items():
        if override or not os.environ.get(key):
            os.environ[key] = value
            applied.append(key)
    return applied


def ensure_loaded() -> None:
    """처음 한 번만 `.env`를 읽는다. 모듈 import 시 자동으로 불린다."""
    global _loaded
    if not _loaded:
        load_env()
        _loaded = True


def available_keys(names: tuple[str, ...]) -> dict[str, bool]:
    """어떤 키가 준비됐는지 확인한다. 값은 노출하지 않는다."""
    ensure_loaded()
    return {name: bool(os.environ.get(name)) for name in names}
