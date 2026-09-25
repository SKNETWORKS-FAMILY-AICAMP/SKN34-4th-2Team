"""Short-lived S3 read URLs for private objects; database values remain object keys."""

from __future__ import annotations

import logging
import os

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

logger = logging.getLogger(__name__)


def signed_read_url(key: str | None, *, expires_in: int = 3600) -> str | None:
    if not key:
        return None
    bucket = os.environ.get("AWS_S3_BUCKET") or os.environ.get("S3_BUCKET")
    region = os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION")
    if not bucket or not region:
        return None
    try:
        client = boto3.client("s3", region_name=region, config=Config(signature_version="s3v4"))
        return client.generate_presigned_url(
            "get_object",
            Params={"Bucket": bucket, "Key": key},
            ExpiresIn=expires_in,
        )
    except (BotoCoreError, ClientError):
        logger.exception("Could not sign S3 read URL")
        return None


# ── 올리기 · 읽기 주소 ─────────────────────────────────────────
# 기록 증빙처럼 화면이 올리는 파일. DB 에는 키만 둔다(record_submission_files.storage_key).
# AWS_S3_BUCKET · AWS_REGION 이 있으면 S3, 없으면(로컬 개발) lms_api/media 에 둔다.
# <img> · <a> 는 로그인 토큰을 못 실어 보내므로 읽기는 잠깐 쓰는 서명 주소로 준다.

LOCAL_ROOT_NAME = "media"
_READ_SALT = "lms.storage.read"
READ_SECONDS = 3600


def _s3_target() -> tuple[str, str] | None:
    bucket = os.environ.get("AWS_S3_BUCKET") or os.environ.get("S3_BUCKET")
    region = os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION")
    return (bucket, region) if bucket and region else None


def _local_root():
    from django.conf import settings

    return settings.BASE_DIR / LOCAL_ROOT_NAME


def local_path(key: str):
    """로컬 저장 위치 — 키가 저장 폴더 밖을 가리키면(../) None"""
    root = _local_root().resolve()
    path = (root / key).resolve()
    return path if root in path.parents else None


def put_object(key: str, data: bytes, content_type: str) -> None:
    target = _s3_target()
    if target:
        bucket, region = target
        client = boto3.client("s3", region_name=region, config=Config(signature_version="s3v4"))
        client.put_object(Bucket=bucket, Key=key, Body=data, ContentType=content_type)
        return
    path = local_path(key)
    if path is None:
        raise ValueError("bad storage key")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def read_url(key: str | None) -> str | None:
    """화면이 여는 주소. 옛 데이터처럼 이미 주소(http)면 그대로 둔다."""
    if not key:
        return None
    if key.startswith(("http://", "https://", "demo://")):
        return key
    if _s3_target():
        return signed_read_url(key, expires_in=READ_SECONDS)
    from urllib.parse import quote

    from django.core import signing

    token = signing.dumps(key, salt=_READ_SALT)
    return f"/api/files?t={quote(token)}"


def key_from_read_token(token: str) -> str | None:
    from django.core import signing

    try:
        return signing.loads(token, salt=_READ_SALT, max_age=READ_SECONDS)
    except signing.BadSignature:
        return None
