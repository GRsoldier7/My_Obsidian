"""
tests/test_brain_dump_orchestrator.py — Orchestrator-level integration tests.

Covers ADR-0005 tests 1, 2, 4, 5, 12 (failure-mode coverage):
  1. MTL append fail  → tasks section retained + status partial
  2. Articles fail    → articles section retained, tasks still cleared
  4. Receipt fail     → no clearing at all + status error
  5. Archive fail     → run aborts before extraction + status error
 12. --no-reset       → outputs written, source untouched, no receipt

Uses a hand-rolled MockS3 (no new pip deps). Failure modes injected by key.

These tests prove the gates ACTUALLY fire on real failure modes — they
caught the pre-fix bug where mtl_result.verified was hardcoded True.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone

import pytest
from botocore.exceptions import ClientError

from tools import bd_integrity as bdi
from tools.process_brain_dump import (
    ARTICLES_FILE,
    MTL_KEY,
    PROCESSED_PREFIX,
    RunLog,
    process_file,
)


# ── Mock S3 ─────────────────────────────────────────────────────────────────


class _MockBody:
    def __init__(self, b: bytes):
        self._b = b

    def read(self) -> bytes:
        return self._b


class MockS3:
    """Minimal in-memory S3 client. Failure injection via `failures` dict
    (exact key) or `fail_prefixes` list (prefix match)."""

    def __init__(self):
        self.objects: dict[str, bytes] = {}
        self.failures: dict[str, Exception] = {}  # "{op}:{exact_key}"
        self.fail_prefixes: list[tuple[str, str, Exception]] = []  # (op, prefix, exc)

    # ── boto3 client surface ────────────────────────────────────────────────

    def head_bucket(self, Bucket):
        self._maybe_fail("head_bucket", Bucket)
        return {}

    def get_object(self, Bucket, Key):
        self._maybe_fail("get_object", Key)
        if Key not in self.objects:
            raise ClientError(
                {"Error": {"Code": "NoSuchKey", "Message": Key}}, "GetObject"
            )
        return {"Body": _MockBody(self.objects[Key])}

    def put_object(self, Bucket, Key, Body):
        self._maybe_fail("put_object", Key)
        if isinstance(Body, str):
            Body = Body.encode("utf-8")
        self.objects[Key] = Body
        return {"ETag": f'"{hashlib.md5(Body).hexdigest()}"'}

    def head_object(self, Bucket, Key):
        self._maybe_fail("head_object", Key)
        if Key not in self.objects:
            raise ClientError(
                {"Error": {"Code": "404", "Message": "Not Found"}}, "HeadObject"
            )
        body = self.objects[Key]
        return {
            "ContentLength": len(body),
            "ETag": f'"{hashlib.md5(body).hexdigest()}"',
        }

    def list_objects_v2(self, Bucket, Prefix=None, **_kw):
        contents = []
        for k, v in self.objects.items():
            if Prefix is None or k.startswith(Prefix):
                contents.append({
                    "Key": k,
                    "Size": len(v),
                    "LastModified": datetime.now(timezone.utc),
                })
        return {"Contents": contents}

    def _maybe_fail(self, op: str, key):
        exact = f"{op}:{key}"
        if exact in self.failures:
            raise self.failures[exact]
        for p_op, p_prefix, exc in self.fail_prefixes:
            if p_op == op and isinstance(key, str) and key.startswith(p_prefix):
                raise exc


# ── Fixtures ────────────────────────────────────────────────────────────────


_SAMPLE_BODY = """\
---
domain: personal
area: personal
status: has_content
content_hash: sha256:placeholder
last_checked: 2026-05-04T07:00:00Z
last_processed: null
last_processed_hash: null
last_receipt: null
last_partial_reasons: []
---

# Brain Dump — Test

## ✅ To Do's

- [ ] Test task one [area:: personal] [priority:: B]

## 📰 Articles & Resources to Follow Up On

- https://example.com/article-one
"""


def _seed_baseline(s3: MockS3) -> None:
    s3.objects[MTL_KEY] = b"# Master Task List\n\nPre-existing content.\n"
    s3.objects[ARTICLES_FILE] = b"# Articles to Process\n\n"


def _seed_source(s3: MockS3, name: str = "Test.md", body: str | None = None) -> str:
    body = body if body is not None else _SAMPLE_BODY
    key = f"00_Inbox/brain-dumps/{name}"
    s3.objects[key] = body.encode("utf-8")
    return key


def _run(s3, src_key: str, name: str = "Test.md", *, no_reset: bool = False) -> RunLog:
    log = RunLog(started_at=bdi.now_utc_iso())
    file_info = {"key": src_key, "name": name, "size": len(s3.objects[src_key])}
    process_file(s3, None, file_info, log, "2026-05-04", dry_run=False, no_reset=no_reset)
    return log


def _server_error(message: str = "simulated") -> ClientError:
    return ClientError(
        {"Error": {"Code": "500", "Message": message}}, "HeadObject"
    )


# ── Tests ────────────────────────────────────────────────────────────────────


def test_mtl_append_failure_retains_tasks_section_status_partial():
    """ADR-0005 Test 1: When MTL write doesn't verify, the tasks section
    must be RETAINED (not cleared) and the file's status must become partial."""
    s3 = MockS3()
    _seed_baseline(s3)
    src = _seed_source(s3)

    # head_object on MTL fails ⇒ s3_put_verified returns False ⇒
    # append_tasks_to_mtl returns verified=False ⇒ section.verified=False
    s3.failures[f"head_object:{MTL_KEY}"] = _server_error("MTL head 500")

    log = _run(s3, src)

    body = s3.objects[src].decode("utf-8")
    assert "Test task one" in body, "tasks section was cleared even though MTL didn't verify"
    assert "[!warning] Retention notice" in body, "no retention block on partial"
    assert "status: partial" in body, "status not flipped to partial"
    assert log.reset_summary["files_reset_partial"] == 1
    assert log.reset_summary["files_reset_full"] == 0


def test_articles_queue_failure_retains_articles_only_tasks_still_cleared():
    """ADR-0005 Test 2: Articles fail ⇒ articles section retained,
    but tasks section verified ⇒ tasks section cleared."""
    s3 = MockS3()
    _seed_baseline(s3)
    src = _seed_source(s3)

    s3.failures[f"head_object:{ARTICLES_FILE}"] = _server_error("articles head 500")

    log = _run(s3, src)

    body = s3.objects[src].decode("utf-8")
    # Articles RETAINED
    assert "https://example.com/article-one" in body, "articles section was wrongly cleared"
    # Tasks CLEARED (their downstream writes verified)
    assert "Test task one" not in body, "tasks section should have been cleared"
    # Retention block present
    assert "[!warning] Retention notice" in body
    # Status partial
    assert "status: partial" in body
    assert log.reset_summary["files_reset_partial"] == 1


def test_receipt_write_failure_refuses_all_clears_status_error():
    """ADR-0005 Test 4: Receipt write (or its head_object) fails ⇒ no
    section clears at all, status flips to error."""
    s3 = MockS3()
    _seed_baseline(s3)
    src = _seed_source(s3)

    # Fail the receipt's head_object verification
    s3.fail_prefixes.append((
        "head_object", "99_System/extraction-receipts/",
        _server_error("receipt head 500"),
    ))

    log = _run(s3, src)

    body = s3.objects[src].decode("utf-8")
    # Source completely untouched downstream of the receipt failure
    assert "Test task one" in body
    assert "https://example.com/article-one" in body
    # Status: error
    assert "status: error" in body
    assert log.reset_summary["files_reset_skipped"] == 1
    assert any("receipt_write_failed" in e for e in log.errors)


def test_archive_write_failure_aborts_run_status_error_no_extraction():
    """ADR-0005 Test 5: Archive head_object fails ⇒ entire run aborts
    BEFORE extraction. MTL is never touched."""
    s3 = MockS3()
    _seed_baseline(s3)
    src = _seed_source(s3)
    mtl_before = s3.objects[MTL_KEY]

    s3.fail_prefixes.append((
        "head_object", "99_System/archive/brain-dumps/",
        _server_error("archive head 500"),
    ))

    log = _run(s3, src)

    body = s3.objects[src].decode("utf-8")
    assert "Test task one" in body, "source should be untouched after archive failure"
    # MTL never touched — extraction never ran
    assert s3.objects[MTL_KEY] == mtl_before, "MTL was modified despite archive abort"
    assert "status: error" in body
    assert log.archive_writes_fail >= 1
    assert log.reset_summary["files_reset_skipped"] >= 1


def test_no_reset_writes_outputs_no_receipt_no_clear():
    """ADR-0005 Test 12: --no-reset writes downstream targets but does NOT
    write a receipt, does NOT clear sections, status stays has_content,
    last_checked DOES advance."""
    s3 = MockS3()
    _seed_baseline(s3)
    src = _seed_source(s3)

    log = _run(s3, src, no_reset=True)

    body = s3.objects[src].decode("utf-8")
    # Source body sections preserved
    assert "Test task one" in body
    assert "https://example.com/article-one" in body
    # Status stays has_content (did NOT reach extracted)
    assert "status: has_content" in body
    # MTL got the task
    mtl = s3.objects[MTL_KEY].decode("utf-8")
    assert "Test task one" in mtl
    # Articles got the URL
    art = s3.objects[ARTICLES_FILE].decode("utf-8")
    assert "https://example.com/article-one" in art
    # NO receipt was written
    receipts = [k for k in s3.objects if k.startswith("99_System/extraction-receipts/")]
    assert receipts == [], f"--no-reset must not write a receipt: {receipts}"
    # NO archive was written
    archives = [k for k in s3.objects if k.startswith("99_System/archive/brain-dumps/")]
    assert archives == [], f"--no-reset must not write an archive: {archives}"


def test_clean_run_extracts_full_writes_receipt_clears_sections():
    """Positive control: when nothing fails, full happy-path runs end-to-end —
    archive + receipt + reset all succeed, source body cleared, status=extracted."""
    s3 = MockS3()
    _seed_baseline(s3)
    src = _seed_source(s3)

    log = _run(s3, src)

    body = s3.objects[src].decode("utf-8")
    assert "Test task one" not in body, "tasks should be cleared on extracted"
    assert "https://example.com/article-one" not in body, "articles should be cleared"
    assert "status: extracted" in body
    assert "[!warning] Retention notice" not in body
    # Receipt + archive both written
    receipts = [k for k in s3.objects if k.startswith("99_System/extraction-receipts/")]
    archives = [k for k in s3.objects if k.startswith("99_System/archive/brain-dumps/")]
    assert len(receipts) == 1, f"expected 1 receipt, got {receipts}"
    assert len(archives) == 1, f"expected 1 archive, got {archives}"
    assert log.reset_summary["files_reset_full"] == 1
    assert log.receipts_written == 1
    assert log.archive_writes_pass == 1
