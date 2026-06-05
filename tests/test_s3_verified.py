"""Tests for tools/s3_verified.py — verified-write helper introduced in
remediation for Codex P1 (2026-05-16)."""
from __future__ import annotations

import sys
from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools import s3_verified as s3v  # noqa: E402


# ── Fixtures ──────────────────────────────────────────────────────────────────
def make_s3_mock(*, get_body: str = "", get_etag: str = '"abc"',
                 head_size: int | None = None) -> MagicMock:
    """Build a MagicMock s3 client whose head/get/put return predictable values."""
    s3 = MagicMock()
    body_bytes = get_body.encode("utf-8")
    body_stream = MagicMock()
    body_stream.read.return_value = body_bytes
    s3.get_object.return_value = {"Body": body_stream, "ETag": get_etag}
    # head_object returns whatever size the test wants (defaults to body length)
    s3._head_size = head_size  # tag for _adjust later
    return s3


def _set_head_size(s3: MagicMock, size: int, etag: str = '"def"') -> None:
    s3.head_object.return_value = {"ContentLength": size, "ETag": etag}


# ── read_text_with_etag ───────────────────────────────────────────────────────
def test_read_text_with_etag_returns_body_and_etag():
    s3 = make_s3_mock(get_body="hello world", get_etag='"abc123"')
    body, etag = s3v.read_text_with_etag(s3, "bucket", "key.md")
    assert body == "hello world"
    assert etag == '"abc123"'


def test_read_text_with_etag_missing_etag_returns_empty():
    s3 = MagicMock()
    body_stream = MagicMock()
    body_stream.read.return_value = b"hi"
    s3.get_object.return_value = {"Body": body_stream}  # no ETag key
    _, etag = s3v.read_text_with_etag(s3, "b", "k")
    assert etag == ""


# ── put_text_verified ─────────────────────────────────────────────────────────
def test_put_text_verified_writes_and_verifies():
    s3 = MagicMock()
    text = "some body"
    _set_head_size(s3, size=len(text.encode("utf-8")), etag='"new-etag"')
    result = s3v.put_text_verified(s3, "b", "k", text)
    assert isinstance(result, s3v.WriteResult)
    assert result.size_bytes == len(text.encode("utf-8"))
    assert result.etag == '"new-etag"'
    # put_object was called with ContentType
    args, kwargs = s3.put_object.call_args
    assert kwargs["Bucket"] == "b"
    assert kwargs["Key"] == "k"
    assert kwargs["Body"] == text.encode("utf-8")
    assert kwargs["ContentType"] == s3v.DEFAULT_TEXT_CONTENT_TYPE


def test_put_text_verified_size_mismatch_raises():
    s3 = MagicMock()
    _set_head_size(s3, size=999)  # lie about the size
    with pytest.raises(s3v.VerificationError) as ei:
        s3v.put_text_verified(s3, "b", "k", "tiny body")
    assert "expected" in str(ei.value)


def test_put_text_verified_content_type_override():
    s3 = MagicMock()
    text = "x"
    _set_head_size(s3, size=1)
    s3v.put_text_verified(s3, "b", "k", text, content_type="application/yaml")
    kwargs = s3.put_object.call_args.kwargs
    assert kwargs["ContentType"] == "application/yaml"


# ── put_text_if_match_verified ────────────────────────────────────────────────
def test_put_text_if_match_verified_happy_path():
    s3 = MagicMock()
    text = "updated"
    _set_head_size(s3, size=len(text.encode("utf-8")))
    result = s3v.put_text_if_match_verified(s3, "b", "k", text, etag='"v1"')
    kwargs = s3.put_object.call_args.kwargs
    assert kwargs["IfMatch"] == '"v1"'
    assert result.size_bytes == len(text.encode("utf-8"))


def test_put_text_if_match_verified_empty_etag_rejected():
    s3 = MagicMock()
    with pytest.raises(ValueError):
        s3v.put_text_if_match_verified(s3, "b", "k", "x", etag="")


def test_put_text_if_match_verified_precondition_failed_translates():
    """A 412 PreconditionFailed becomes PreconditionFailedError so callers can retry."""
    s3 = MagicMock()
    err = s3v.ClientError(
        {"Error": {"Code": "PreconditionFailed"},
         "ResponseMetadata": {"HTTPStatusCode": 412}},
        "PutObject",
    )
    s3.put_object.side_effect = err
    with pytest.raises(s3v.PreconditionFailedError):
        s3v.put_text_if_match_verified(s3, "b", "k", "x", etag='"old"')


def test_put_text_if_match_verified_other_error_propagates():
    """Non-412 ClientErrors are NOT swallowed — they bubble unchanged."""
    s3 = MagicMock()
    err = s3v.ClientError(
        {"Error": {"Code": "AccessDenied"},
         "ResponseMetadata": {"HTTPStatusCode": 403}},
        "PutObject",
    )
    s3.put_object.side_effect = err
    with pytest.raises(s3v.ClientError):
        s3v.put_text_if_match_verified(s3, "b", "k", "x", etag='"old"')


# ── put_json_verified ─────────────────────────────────────────────────────────
def test_put_json_verified_serializes_and_writes():
    s3 = MagicMock()
    payload = {"status": "ok", "count": 3}
    import json as _json
    expected_text = _json.dumps(payload, indent=2, default=str)
    _set_head_size(s3, size=len(expected_text.encode("utf-8")))
    result = s3v.put_json_verified(s3, "b", "k.json", payload)
    assert result.size_bytes == len(expected_text.encode("utf-8"))
    kwargs = s3.put_object.call_args.kwargs
    assert kwargs["ContentType"] == s3v.DEFAULT_JSON_CONTENT_TYPE
    assert kwargs["Body"].decode("utf-8") == expected_text


def test_put_json_verified_handles_non_jsonable_with_default_str():
    """default=str makes datetime / Path / dataclass instances survive serialization."""
    s3 = MagicMock()
    from datetime import datetime, timezone
    payload = {"ts": datetime(2026, 5, 16, tzinfo=timezone.utc)}
    import json as _json
    expected_text = _json.dumps(payload, indent=2, default=str)
    _set_head_size(s3, size=len(expected_text.encode("utf-8")))
    result = s3v.put_json_verified(s3, "b", "k.json", payload)
    assert result.size_bytes == len(expected_text.encode("utf-8"))


# ── WriteResult repr ──────────────────────────────────────────────────────────
def test_writeresult_repr_short_and_useful():
    r = s3v.WriteResult(key="k", etag='"e"', size_bytes=42, head={"x": 1})
    rep = repr(r)
    assert "k" in rep
    assert "42" in rep
    assert "head" not in rep  # `head` dict isn't blown into the repr
