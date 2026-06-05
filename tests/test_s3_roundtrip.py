"""
tests/test_s3_roundtrip.py
Tests for MinIO S3 write-and-verify pattern in tools/process_brain_dump.py.

Verifies:
- s3_put_verified writes AND confirms via head_object
- s3_put_verified returns False on write failure
- s3_put_verified returns False when head_object fails (write appeared to succeed but isn't readable)
- dry_run mode skips all S3 operations
- discover_brain_dumps correctly lists non-empty files
"""
import sys
import os
from unittest.mock import MagicMock, patch, call

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
from process_brain_dump import s3_put_verified, discover_brain_dumps, BRAIN_DUMPS_PREFIX


# ── s3_put_verified ───────────────────────────────────────────────────────────

def test_put_verified_success():
    """Happy path: put_object succeeds, head_object confirms write."""
    s3 = MagicMock()
    s3.head_object.return_value = {"ContentLength": 42}

    result = s3_put_verified(s3, "some/key.md", "some content")

    assert result is True
    s3.put_object.assert_called_once()
    s3.head_object.assert_called_once()


def test_put_verified_calls_head_object_after_put():
    """s3_put_verified must call head_object to verify — not just trust the put."""
    s3 = MagicMock()
    s3.head_object.return_value = {"ContentLength": 100}
    call_order = []

    def track_put(*args, **kwargs):
        call_order.append("put")
    def track_head(*args, **kwargs):
        call_order.append("head")
        return {"ContentLength": 100}

    s3.put_object.side_effect = track_put
    s3.head_object.side_effect = track_head

    s3_put_verified(s3, "key.md", "content")

    assert call_order == ["put", "head"], "head_object must be called AFTER put_object"


def test_put_verified_write_failure_returns_false():
    """If put_object raises, s3_put_verified returns False."""
    from botocore.exceptions import ClientError
    s3 = MagicMock()
    s3.put_object.side_effect = ClientError(
        {"Error": {"Code": "AccessDenied", "Message": "denied"}}, "PutObject"
    )

    result = s3_put_verified(s3, "key.md", "content")

    assert result is False


def test_put_verified_head_object_fails_returns_false():
    """If put succeeds but head_object raises, s3_put_verified returns False.
    This catches the case where the write appeared to succeed but the file
    can't be confirmed — could be a consistency issue or immediate deletion."""
    from botocore.exceptions import ClientError
    s3 = MagicMock()
    s3.put_object.return_value = {}  # put "succeeds"
    s3.head_object.side_effect = ClientError(
        {"Error": {"Code": "404", "Message": "Not Found"}}, "HeadObject"
    )

    result = s3_put_verified(s3, "key.md", "content")

    assert result is False


def test_put_verified_head_object_zero_length_returns_false():
    """ContentLength of 0 indicates empty write — should return False."""
    s3 = MagicMock()
    s3.head_object.return_value = {"ContentLength": 0}

    result = s3_put_verified(s3, "key.md", "content")

    assert result is False


def test_put_verified_dry_run_skips_s3():
    """In dry_run mode, no S3 operations are performed — returns True."""
    s3 = MagicMock()

    result = s3_put_verified(s3, "key.md", "content", dry_run=True)

    assert result is True
    s3.put_object.assert_not_called()
    s3.head_object.assert_not_called()


def test_put_verified_encodes_utf8():
    """s3_put_verified encodes content as UTF-8 bytes for the put."""
    s3 = MagicMock()
    s3.head_object.return_value = {"ContentLength": 10}
    content = "Hello café"

    s3_put_verified(s3, "key.md", content)

    put_call = s3.put_object.call_args
    body = put_call.kwargs.get("Body") or put_call[1].get("Body")
    assert body == content.encode("utf-8")


def test_put_verified_uses_correct_bucket(monkeypatch):
    """s3_put_verified writes to MINIO_BUCKET env var, not a hardcoded bucket."""
    monkeypatch.setenv("MINIO_BUCKET", "obsidian-vault")
    # Re-import to pick up new env
    import importlib
    import process_brain_dump as pbd
    importlib.reload(pbd)

    s3 = MagicMock()
    s3.head_object.return_value = {"ContentLength": 5}

    pbd.s3_put_verified(s3, "key.md", "hello")

    put_call = s3.put_object.call_args
    bucket = put_call.kwargs.get("Bucket") or put_call[1].get("Bucket")
    assert bucket == "obsidian-vault"


# ── discover_brain_dumps ──────────────────────────────────────────────────────

def test_discover_brain_dumps_returns_non_empty_files():
    """discover_brain_dumps returns only files with content (size > 0)."""
    s3 = MagicMock()
    s3.list_objects_v2.return_value = {
        "Contents": [
            {"Key": "00_Inbox/brain-dumps/BrainDump-Personal.md", "Size": 512},
            {"Key": "00_Inbox/brain-dumps/BrainDump-Work.md", "Size": 0},     # empty
            {"Key": "00_Inbox/brain-dumps/", "Size": 0},                       # folder placeholder
        ]
    }

    files = discover_brain_dumps(s3)

    assert len(files) == 1
    assert files[0]["name"] == "BrainDump-Personal.md"
    assert files[0]["size"] == 512


def test_discover_brain_dumps_empty_bucket():
    """No files in bucket → empty list, no exceptions."""
    s3 = MagicMock()
    s3.list_objects_v2.return_value = {"Contents": []}

    files = discover_brain_dumps(s3)

    assert files == []


def test_discover_brain_dumps_uses_correct_prefix():
    """discover_brain_dumps lists from BRAIN_DUMPS_PREFIX, not bucket root."""
    s3 = MagicMock()
    s3.list_objects_v2.return_value = {"Contents": []}

    discover_brain_dumps(s3)

    call_kwargs = s3.list_objects_v2.call_args.kwargs
    assert call_kwargs.get("Prefix") == BRAIN_DUMPS_PREFIX


def test_discover_brain_dumps_no_contents_key():
    """Gracefully handles response with no 'Contents' key (empty prefix)."""
    s3 = MagicMock()
    s3.list_objects_v2.return_value = {}  # no Contents key

    files = discover_brain_dumps(s3)

    assert files == []


def test_discover_brain_dumps_multiple_files():
    """Returns all non-empty files as dicts with key/name/size."""
    s3 = MagicMock()
    s3.list_objects_v2.return_value = {
        "Contents": [
            {"Key": "00_Inbox/brain-dumps/BrainDump-Personal.md", "Size": 100},
            {"Key": "00_Inbox/brain-dumps/BrainDump-Work.md", "Size": 200},
            {"Key": "00_Inbox/brain-dumps/BrainDump-Faith.md", "Size": 300},
        ]
    }

    files = discover_brain_dumps(s3)

    assert len(files) == 3
    names = {f["name"] for f in files}
    assert names == {"BrainDump-Personal.md", "BrainDump-Work.md", "BrainDump-Faith.md"}
