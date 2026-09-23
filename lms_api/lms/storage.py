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
