"""공고 데이터를 팀원과 나눈다. 저장소에서 필요한 것만 뽑아 Firebase Storage로 주고받는다.

    python -m job_matching_bot.sharing.share_store --export            # 슬림 파일 만들기
    python -m job_matching_bot.sharing.share_store --export --upload   # 만들어서 올리기
    python -m job_matching_bot.sharing.share_store --download          # 받아서 제자리에 놓기 (팀원용)
    python -m job_matching_bot.sharing.share_store --download-if-newer # 새 generation만 안전 교체
    python -m job_matching_bot.sharing.share_store --info              # 올라가 있는 파일 정보

## 왜 필요한가

추천은 Pinecone만 보므로 키만 있으면 팀원도 그대로 쓴다. 그런데 **첨삭은 공고 원문 전체**가
필요하고, 그건 수집한 사람의 `artifacts/job_store.sqlite`에만 있다. Pinecone 메타데이터에는
1,200자 발췌만 들어 있어서 뒤쪽 요건을 놓친다.

그래서 저장소를 통째로 주는 대신, 읽는 쪽에 필요한 컬럼만 담은 작은 파일을 만들어
올린다. 87MB → 약 30MB, 압축하면 10MB 안팎이다.

## 무엇을 빼는가

- `field_provenance` (14MB) — 어느 규칙으로 그 값을 뽑았는지 남긴 개발용 기록.
  **컬럼은 남기고 내용만 비운다.** `SqliteJobStore`가 공고를 읽을 때 이 컬럼을 찾으므로
  아예 없애면 받는 쪽 코드가 깨진다. 빈 값이라 용량은 그대로 아낀다
- `job_tags` 표 (18만 행) — 조회 편의용 색인. 원본은 컬럼에 그대로 있다
- 인덱스 추적 컬럼 — 수집한 사람만 쓴다

읽는 쪽(첨삭)이 실제로 쓰는 값은 전부 남는다.

## 왜 Firestore가 아니라 파일인가

Firestore는 앱이 공고를 직접 읽어야 할 때 필요하다. 지금 막힌 것은 앱이 아니라 팀원의
서버이고, 서버는 파일을 받아 두면 로컬에서 훨씬 빠르게 읽는다. 저장소가 전 카테고리로
커져도 파일이 커질 뿐 문서 수·쓰기 한도에 걸리지 않는다.
"""

from __future__ import annotations

import argparse
import gzip
import json
import os
import shutil
import sqlite3
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

from job_matching_bot.config import ARTIFACTS_DIR

# 기본 버킷. Firebase 콘솔의 Storage 주소와 같다.
DEFAULT_BUCKET = "skn34-3rd-2team.firebasestorage.app"
# 버킷 안의 경로. 늘 같은 이름으로 덮어써서 받는 쪽이 주소를 외우지 않아도 되게 한다.
REMOTE_PATH = "job_matching_bot/job_store_share.sqlite.gz"

DEFAULT_STORE = ARTIFACTS_DIR / "job_store.sqlite"
EXPORT_PATH = ARTIFACTS_DIR / "job_store_share.sqlite"

# 나눠 줄 컬럼. 공고를 읽고 판단하는 데 필요한 것만.
SHARE_COLUMNS = (
    "job_id", "source", "source_job_id", "source_url",
    "company", "company_type", "title", "description",
    "required_skills", "preferred_skills", "tech_stack", "keywords",
    "career_type", "min_career_years", "education", "region", "employment_type",
    "posted_at", "deadline", "status", "content_hash", "parser_version",
    "body_is_image", "required_majors", "required_major_terms",
    "required_certifications", "military_required",
    "first_seen_at", "last_seen_at", "missing_runs", "revisions",
)
# 값은 필요 없지만 컬럼은 있어야 하는 것. 받는 쪽 `SqliteJobStore`가 찾는다.
EMPTY_COLUMNS = {"field_provenance": "'{}'"}
REQUIRED_DOWNLOAD_COLUMNS = frozenset({*SHARE_COLUMNS, *EMPTY_COLUMNS})


def export(source: Path, destination: Path) -> Path:
    """저장소에서 나눠 줄 컬럼만 뽑아 새 SQLite로 만든다. 원본은 건드리지 않는다."""
    from job_matching_bot.ingestion.sqlite_store import SqliteJobStore, _BOOL_FIELDS, _JSON_FIELDS

    if destination.exists():
        destination.unlink()
    destination.parent.mkdir(parents=True, exist_ok=True)

    store = SqliteJobStore(source)
    try:
        available = store._table_columns("jobs")
        columns = [name for name in SHARE_COLUMNS if name in available]
        missing = [name for name in SHARE_COLUMNS if name not in available]
        if missing:
            print(f"  (저장소에 없는 컬럼은 건너뜁니다: {', '.join(missing)})")
        all_columns = columns + [name for name in EMPTY_COLUMNS if name in available]
        definition = ", ".join(
            f"{name} INTEGER" + (" PRIMARY KEY" if name == "job_id" else "")
            if name in _BOOL_FIELDS or name in {"min_career_years", "missing_runs", "revisions"}
            else f"{name} TEXT" + (" PRIMARY KEY" if name == "job_id" else "")
            for name in all_columns
        )
        dest = sqlite3.connect(str(destination))
        dest.execute(f"CREATE TABLE jobs ({definition})")
        dest.execute("CREATE INDEX jobs_status ON jobs(status)")
        placeholders = ", ".join("?" for _ in all_columns)
        insert = f"INSERT INTO jobs ({', '.join(all_columns)}) VALUES ({placeholders})"
        rows = 0
        for record in store.iter_records():
            values = []
            for name in all_columns:
                if name in EMPTY_COLUMNS:
                    values.append("{}")
                    continue
                if name in ("first_seen_at", "last_seen_at", "missing_runs", "revisions"):
                    raw = getattr(record, name)
                else:
                    raw = getattr(record.job, name)
                if name in _JSON_FIELDS:
                    raw = json.dumps(raw if raw is not None else ([] if name != "field_provenance" else {}), ensure_ascii=False)
                elif name in _BOOL_FIELDS:
                    raw = 1 if raw else 0
                values.append(raw)
            dest.execute(insert, values)
            rows += 1
        dest.commit()
        dest.execute("VACUUM")
        dest.close()
    finally:
        store.close()

    print(f"  공고 {rows:,}건 · {_mb(destination):.1f} MB → {destination}")
    return destination


def compress(path: Path) -> Path:
    """gzip으로 압축한다. 올릴 때 시간과 용량을 줄인다."""
    target = path.with_suffix(path.suffix + ".gz")
    with path.open("rb") as src, gzip.open(target, "wb", compresslevel=9) as dst:
        shutil.copyfileobj(src, dst)
    print(f"  압축 {_mb(path):.1f} MB → {_mb(target):.1f} MB")
    return target


def decompress(path: Path, destination: Path) -> Path:
    with gzip.open(path, "rb") as src, destination.open("wb") as dst:
        shutil.copyfileobj(src, dst)
    return destination


def bucket(name: str):
    """Firebase Storage 버킷. 인증은 gcloud application-default 자격증명을 쓴다."""
    import firebase_admin
    from firebase_admin import credentials, storage

    try:
        app = firebase_admin.get_app()
    except ValueError:
        app = firebase_admin.initialize_app(
            credentials.ApplicationDefault(), {"storageBucket": name}
        )
    return storage.bucket(name, app=app)


def upload(path: Path, bucket_name: str, remote: str = REMOTE_PATH) -> str:
    blob = bucket(bucket_name).blob(remote)
    started = time.time()
    blob.upload_from_filename(str(path))
    print(f"  올림 {_mb(path):.1f} MB · {time.time() - started:.0f}초 → gs://{bucket_name}/{remote}")
    return remote


def download(bucket_name: str, destination: Path, remote: str = REMOTE_PATH) -> Path:
    """올라가 있는 파일을 받아 압축을 풀고 제자리에 놓는다."""
    blob = bucket(bucket_name).blob(remote)
    if not blob.exists():
        raise FileNotFoundError(f"버킷에 파일이 없습니다: gs://{bucket_name}/{remote}")
    blob.reload()
    destination.parent.mkdir(parents=True, exist_ok=True)
    archive = destination.with_suffix(destination.suffix + ".gz")
    started = time.time()
    blob.download_to_filename(str(archive))
    decompress(archive, destination)
    archive.unlink()
    print(f"  받음 {_mb(destination):.1f} MB · {time.time() - started:.0f}초 → {destination}")
    print(f"  올라간 시각: {blob.updated}")
    return destination


def _download_state_path(destination: Path) -> Path:
    return destination.with_name(f"{destination.stem}.remote.json")


def _remote_version(blob) -> dict[str, str | int]:
    updated = blob.updated
    if hasattr(updated, "isoformat"):
        updated = updated.isoformat()
    return {
        "generation": str(blob.generation or ""),
        "updated": str(updated or ""),
        "size": int(blob.size or 0),
    }


def _read_download_state(destination: Path) -> dict:
    try:
        return json.loads(_download_state_path(destination).read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def validate_download(path: Path) -> int:
    """받은 파일이 추천·첨삭 서버에서 읽을 수 있는 SQLite인지 검사한다."""
    connection = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
    try:
        integrity = connection.execute("PRAGMA quick_check").fetchone()
        if not integrity or integrity[0] != "ok":
            raise ValueError(f"SQLite 무결성 검사 실패: {integrity}")
        tables = {
            row[0] for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        if "jobs" not in tables:
            raise ValueError("공유 DB에 jobs 테이블이 없습니다")
        columns = {row[1] for row in connection.execute("PRAGMA table_info(jobs)")}
        missing = sorted(REQUIRED_DOWNLOAD_COLUMNS - columns)
        if missing:
            raise ValueError(f"공유 DB 필수 컬럼 누락: {', '.join(missing)}")
        count = int(connection.execute("SELECT COUNT(*) FROM jobs").fetchone()[0])
        if count <= 0:
            raise ValueError("공유 DB에 공고가 없습니다")
        return count
    finally:
        connection.close()


def download_if_newer(
    bucket_name: str, destination: Path, remote: str = REMOTE_PATH,
) -> bool:
    """원격 generation이 바뀐 경우에만 검증된 SQLite로 원자 교체한다."""
    blob = bucket(bucket_name).blob(remote)
    if not blob.exists():
        raise FileNotFoundError(f"버킷에 파일이 없습니다: gs://{bucket_name}/{remote}")
    blob.reload()
    version = _remote_version(blob)
    previous = _read_download_state(destination)
    if destination.is_file() and previous.get("generation") == version["generation"]:
        print(f"  최신 공유 DB를 이미 사용 중입니다 (generation {version['generation']})")
        return False

    destination.parent.mkdir(parents=True, exist_ok=True)
    archive_fd, archive_name = tempfile.mkstemp(
        prefix=f".{destination.stem}-", suffix=".sqlite.gz", dir=destination.parent,
    )
    database_fd, database_name = tempfile.mkstemp(
        prefix=f".{destination.stem}-", suffix=".sqlite", dir=destination.parent,
    )
    os.close(archive_fd)
    os.close(database_fd)
    archive = Path(archive_name)
    database = Path(database_name)
    started = time.time()
    try:
        blob.download_to_filename(str(archive))
        decompress(archive, database)
        count = validate_download(database)
        os.replace(database, destination)
        for suffix in ("-wal", "-shm"):
            sidecar = Path(f"{destination}{suffix}")
            if sidecar.exists():
                sidecar.unlink()
        state = {
            **version,
            "downloaded_at": datetime.now(timezone.utc).isoformat(),
            "job_count": count,
        }
        state_path = _download_state_path(destination)
        temporary_state = state_path.with_suffix(state_path.suffix + ".tmp")
        temporary_state.write_text(
            json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        os.replace(temporary_state, state_path)
        print(
            f"  최신 공유 DB로 교체했습니다: 공고 {count:,}건 · "
            f"{_mb(destination):.1f} MB · {time.time() - started:.0f}초"
        )
        print(f"  원격 갱신 시각: {version['updated']}")
        return True
    finally:
        archive.unlink(missing_ok=True)
        database.unlink(missing_ok=True)


def info(bucket_name: str, remote: str = REMOTE_PATH) -> int:
    blob = bucket(bucket_name).blob(remote)
    if not blob.exists():
        print(f"아직 올라간 파일이 없습니다: gs://{bucket_name}/{remote}")
        return 1
    blob.reload()
    print(f"gs://{bucket_name}/{remote}")
    print(f"  크기      {blob.size / 1048576:.1f} MB")
    print(f"  올린 시각 {blob.updated}")
    return 0


def _mb(path: Path) -> float:
    return path.stat().st_size / 1048576


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="공고 데이터 공유")
    parser.add_argument("--export", action="store_true", help="나눠 줄 슬림 파일을 만든다")
    parser.add_argument("--upload", action="store_true", help="만든 파일을 Storage에 올린다")
    parser.add_argument("--download", action="store_true", help="Storage에서 받아 제자리에 놓는다")
    parser.add_argument(
        "--download-if-newer",
        action="store_true",
        help="원격 파일이 바뀐 경우에만 검증 후 원자적으로 교체",
    )
    parser.add_argument("--info", action="store_true", help="올라가 있는 파일 정보")
    parser.add_argument("--store", type=Path, default=DEFAULT_STORE)
    parser.add_argument("--out", type=Path, default=EXPORT_PATH)
    parser.add_argument("--bucket", default=DEFAULT_BUCKET)
    args = parser.parse_args()

    if args.info:
        return info(args.bucket)

    if args.download:
        # 받는 쪽은 이 파일을 저장소 자리에 놓는다. 첨삭 서버가 기본으로 그 경로를 본다.
        download(args.bucket, args.store)
        return 0

    if args.download_if_newer:
        download_if_newer(args.bucket, args.store)
        return 0

    if args.export:
        if not args.store.exists():
            print(f"저장소가 없습니다: {args.store}")
            return 1
        slim = export(args.store, args.out)
        archive = compress(slim)
        if args.upload:
            upload(archive, args.bucket)
        return 0

    if args.upload:
        archive = args.out.with_suffix(args.out.suffix + ".gz")
        if not archive.exists():
            print(f"올릴 파일이 없습니다: {archive} (먼저 --export)")
            return 1
        upload(archive, args.bucket)
        return 0

    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
