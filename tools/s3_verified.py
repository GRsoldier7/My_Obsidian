"""
tools/s3_verified.py — single source of truth for verified S3 writes.

Born from the 2026-05-16 Codex review (P1):
> centralize S3 writes in one verified helper. Require exact byte-length or
> byte-exact readback, add IfMatch for read-modify-write paths.

Today's call sites in tools/ and scripts/ each implement their own write+verify
sequence. The helpers diverge: some check ContentLength, some don't; some return
ETag, some don't; backfill uses IfMatch, archive doesn't, telemetry has no ETag
at all. This module collapses the divergence to four functions:

    read_text_with_etag(s3, bucket, key) -> (text, etag)
    put_text_verified(s3, bucket, key, text, content_type=...) -> WriteResult
    put_text_if_match_verified(s3, bucket, key, text, etag, content_type=...)
    put_json_verified(s3, bucket, key, payload, content_type="application/json")

Every put_* function:
  1. Sends the body to S3.
  2. Calls head_object on the same key.
  3. Verifies head.ContentLength == len(body_bytes) — fails loud if not.
  4. Returns a WriteResult with etag, size_bytes, and head_response.

Read-modify-write callers MUST use `put_text_if_match_verified` to pass the
ETag they captured in `read_text_with_etag`. A `PreconditionFailedError` is
raised if a concurrent writer changed the object between read and write.

This module is ADDITIVE. Existing call sites are not rewritten in the same
commit; call-site migration is a separate post-soak task (per ADR-0007).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

try:
    from botocore.exceptions import ClientError
except ImportError:  # pragma: no cover — boto3 missing only in barebones envs
    class ClientError(Exception):  # type: ignore[no-redef]
        def __init__(self, response: dict, op: str) -> None:
            super().__init__(f"{op} failed: {response}")
            self.response = response
            self.operation_name = op


DEFAULT_TEXT_CONTENT_TYPE = "text/markdown; charset=utf-8"
DEFAULT_JSON_CONTENT_TYPE = "application/json"


class PreconditionFailedError(RuntimeError):
    """Raised when an If-Match put hit a concurrent write."""


class VerificationError(RuntimeError):
    """Raised when head_object disagrees with the write we just made."""


@dataclass
class WriteResult:
    key: str
    etag: str
    size_bytes: int
    head: dict[str, Any]

    def __repr__(self) -> str:
        return f"WriteResult(key={self.key!r}, etag={self.etag!r}, size={self.size_bytes})"


def _encode(text: str) -> bytes:
    return text.encode("utf-8")


def read_text_with_etag(s3, bucket: str, key: str) -> tuple[str, str]:
    """Fetch an object's body + ETag in one trip. The ETag is the read-side
    handle that callers MUST pass back to put_text_if_match_verified to detect
    concurrent writers."""
    resp = s3.get_object(Bucket=bucket, Key=key)
    body = resp["Body"].read().decode("utf-8")
    etag = resp.get("ETag") or ""
    return body, etag


def _verify(s3, bucket: str, key: str, expected_size: int) -> WriteResult:
    head = s3.head_object(Bucket=bucket, Key=key)
    actual = head["ContentLength"]
    if actual != expected_size:
        raise VerificationError(
            f"S3 verification failed for s3://{bucket}/{key}: "
            f"expected {expected_size} bytes, head reports {actual}"
        )
    return WriteResult(
        key=key,
        etag=head.get("ETag", ""),
        size_bytes=actual,
        head=head,
    )


def put_text_verified(
    s3,
    bucket: str,
    key: str,
    text: str,
    *,
    content_type: str = DEFAULT_TEXT_CONTENT_TYPE,
) -> WriteResult:
    """Write text + head_object check. Use for new-object writes where the
    object did not exist before (no concurrency concern)."""
    body = _encode(text)
    s3.put_object(
        Bucket=bucket,
        Key=key,
        Body=body,
        ContentType=content_type,
    )
    return _verify(s3, bucket, key, len(body))


def put_text_if_match_verified(
    s3,
    bucket: str,
    key: str,
    text: str,
    etag: str,
    *,
    content_type: str = DEFAULT_TEXT_CONTENT_TYPE,
) -> WriteResult:
    """Write text with an If-Match ETag guard + head_object verification.

    Use this for every read-modify-write path: the caller passes the ETag
    captured by `read_text_with_etag`, and S3 rejects the put with
    PreconditionFailed if another writer raced us. We translate that into
    `PreconditionFailedError` so callers can retry the read-modify cycle.
    """
    if not etag:
        raise ValueError("put_text_if_match_verified requires a non-empty ETag")
    body = _encode(text)
    try:
        s3.put_object(
            Bucket=bucket,
            Key=key,
            Body=body,
            ContentType=content_type,
            IfMatch=etag,
        )
    except ClientError as e:
        code = e.response.get("Error", {}).get("Code", "")
        status = e.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
        if code == "PreconditionFailed" or status == 412:
            raise PreconditionFailedError(
                f"Concurrent write detected on s3://{bucket}/{key} "
                f"(If-Match {etag} no longer matches)"
            ) from e
        raise
    return _verify(s3, bucket, key, len(body))


def put_json_verified(
    s3,
    bucket: str,
    key: str,
    payload,
    *,
    content_type: str = DEFAULT_JSON_CONTENT_TYPE,
    indent: int = 2,
) -> WriteResult:
    """Serialize + write JSON + verify. Wraps `put_text_verified`."""
    import json
    text = json.dumps(payload, indent=indent, default=str)
    return put_text_verified(s3, bucket, key, text, content_type=content_type)
