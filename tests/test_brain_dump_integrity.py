"""
tests/test_brain_dump_integrity.py — P1 step-2 tests for tools/bd_integrity.

Covers the pure-function tests called out in ADR-0005:
  3, 6, 11, 13, 15, 16  + receipt/state-machine/serialization scaffolding.

Orchestrator-level tests (1, 2, 4, 5, 7, 8, 9, 10, 12, 14) land in step 4
when the live processor is wired to bd_integrity.
"""
from __future__ import annotations

import pytest

from tools import bd_integrity as bdi


SIMPLE_BODY = """
# Brain Dump — Faith

## Quick Notes

Some real content here.

## To Do's

- [ ] Pray for clarity
"""


# ── Test 6 (subset): canary roundtrip — pure pipeline ────────────────────────

def test_compute_content_hash_is_deterministic():
    h1 = bdi.compute_content_hash(SIMPLE_BODY)
    h2 = bdi.compute_content_hash(SIMPLE_BODY)
    assert h1 == h2
    assert h1.startswith("sha256:")


def test_compute_content_hash_normalizes_line_endings():
    base = bdi.compute_content_hash(SIMPLE_BODY)
    crlf = bdi.compute_content_hash(SIMPLE_BODY.replace("\n", "\r\n"))
    cr = bdi.compute_content_hash(SIMPLE_BODY.replace("\n", "\r"))
    assert base == crlf == cr


# ── Test 11: content_hash excludes retention block ───────────────────────────

def test_content_hash_excludes_retention_block():
    base = bdi.compute_content_hash(SIMPLE_BODY)
    retention = (
        "> [!warning] Retention notice — 2026-05-04\n"
        "> The following sections were NOT cleared because their downstream writes failed:\n"
        "> - **To Do's** — mtl write failed (head_object 503)\n"
        ">\n"
        "> Receipt: [[99_System/extraction-receipts/Faith-20260504-abcd1234]]\n"
        "> The next scheduled run will retry these sections automatically.\n"
        "\n"
    )
    body_with_retention = retention + SIMPLE_BODY
    assert bdi.compute_content_hash(body_with_retention) == base


def test_strip_retention_block_idempotent():
    plain = SIMPLE_BODY
    retention = (
        "> [!warning] Retention notice — 2026-05-04\n"
        "> Some sections failed.\n"
        "> - **X** — reason\n"
        ">\n"
        "> Receipt: [[receipts/X-20260504-abc12345]]\n"
        "> The next scheduled run will retry these sections automatically.\n\n"
    )
    once = bdi.strip_retention_block(retention + plain)
    twice = bdi.strip_retention_block(once)
    assert once == twice
    assert "Retention notice" not in once
    assert "Quick Notes" in once  # body preserved


# ── Test 13: idempotent receipt path ─────────────────────────────────────────

def test_receipt_path_is_content_addressed():
    h = "sha256:3a9c2f1b" + "0" * 56
    p1 = bdi.receipt_path("Faith.md", "20260504", h)
    p2 = bdi.receipt_path("Faith.md", "20260504", h)
    assert p1 == p2
    assert p1.startswith("99_System/extraction-receipts/")
    assert p1.endswith(".json")
    assert "Faith-20260504-3a9c2f1b" in p1


def test_receipt_path_handles_spaces_and_emdashes():
    h = "sha256:abcd1234" + "0" * 56
    p = bdi.receipt_path("BrainDump — Personal.md", "20260504", h)
    # spaces/em-dashes collapse to a single hyphen
    assert "BrainDump-Personal-20260504-abcd1234" in p


def test_receipt_path_truncates_hash_to_8_hex():
    h = "sha256:" + "a" * 64
    p = bdi.receipt_path("Faith.md", "20260504", h)
    assert "Faith-20260504-aaaaaaaa.json" in p
    # 8 a's, not 9
    assert "aaaaaaaaa" not in p


def test_archive_path_uses_dashed_date_folder():
    p = bdi.archive_path("Faith.md", "20260504")
    assert p == "99_System/archive/brain-dumps/2026-05-04/Faith.md"


# ── Test 15: frontmatter migration idempotent ────────────────────────────────

def test_migrate_frontmatter_idempotent_with_content():
    fm = {"domain": "personal", "area": "personal", "status": "has_content"}
    now = "2026-05-04T07:00:00Z"

    once = bdi.migrate_frontmatter(fm, SIMPLE_BODY, now)
    twice = bdi.migrate_frontmatter(once, SIMPLE_BODY, now)

    assert once == twice
    assert once["content_hash"].startswith("sha256:")
    assert once["last_checked"] == now
    assert once["status"] == "has_content"  # body has real content
    assert once["last_processed"] is None
    assert once["last_processed_hash"] is None
    assert once["last_partial_reasons"] == []
    assert once["last_receipt"] is None


def test_migrate_frontmatter_idempotent_with_empty_body():
    fm: dict = {"domain": "faith", "area": "faith"}
    empty_body = (
        "\n# Brain Dump\n\n"
        "> **How to use:** template content only.\n\n"
        "## Quick Notes\n\n"
        "<!-- Add notes here -->\n"
    )
    now = "2026-05-04T07:00:00Z"

    once = bdi.migrate_frontmatter(fm, empty_body, now)
    twice = bdi.migrate_frontmatter(once, empty_body, now)

    assert once == twice
    assert once["status"] == "empty"
    # When empty, last_processed_hash matches current_hash to avoid false "edited since"
    assert once["last_processed_hash"] == once["content_hash"]
    assert once["last_processed"] == now


def test_migrate_frontmatter_preserves_unknown_legacy_fields():
    fm = {"domain": "faith", "area": "faith", "legacy_field_xyz": "preserved"}
    once = bdi.migrate_frontmatter(fm, SIMPLE_BODY, "2026-05-04T07:00:00Z")
    assert once["legacy_field_xyz"] == "preserved"


def test_migrate_frontmatter_clears_stale_last_processed_on_has_content():
    """When status flips to has_content, legacy last_processed must be wiped —
    otherwise the audit sees `last_processed` set but `last_processed_hash` null.
    Regression: caught in 2026-05-03 verification pass."""
    fm = {
        "domain": "personal",
        "area": "personal",
        "status": "empty",
        "last_processed": "2026-04-20",  # stale legacy value
    }
    out = bdi.migrate_frontmatter(fm, SIMPLE_BODY, "2026-05-04T07:00:00Z")
    assert out["status"] == "has_content"
    assert out["last_processed"] is None
    assert out["last_processed_hash"] is None


# ── Test 3: partial success writes retention block with reasons ──────────────

def test_make_retention_block_format():
    block = bdi.make_retention_block(
        "2026-05-04",
        failed_sections=[
            {"section": "📰 Articles", "reason": "articles_queue write failed (head_object 503)"},
        ],
        receipt_key="99_System/extraction-receipts/Faith-20260504-abcd1234.json",
    )
    assert "[!warning] Retention notice — 2026-05-04" in block
    assert "📰 Articles" in block
    assert "head_object 503" in block
    # Receipt wikilink with .json stripped
    assert "[[99_System/extraction-receipts/Faith-20260504-abcd1234]]" in block
    # Re-grounding line for the user
    assert "next scheduled run will retry" in block


def test_make_retention_block_handles_iso_date():
    block = bdi.make_retention_block(
        "2026-05-04T07:00:00Z",
        failed_sections=[{"section": "X", "reason": "y"}],
        receipt_key="99_System/extraction-receipts/X-20260504-aaaaaaaa.json",
    )
    assert "Retention notice — 2026-05-04" in block


# ── Test 16: partial-to-extracted clears retention block ─────────────────────

def test_apply_reset_clears_retention_when_all_verified():
    """When all sections verify on retry, the retention block from the prior
    partial run gets stripped."""
    content = (
        "---\n"
        "domain: faith\n"
        "area: faith\n"
        "status: partial\n"
        "---\n"
        "\n"
        "> [!warning] Retention notice — 2026-05-03\n"
        "> The following sections were NOT cleared because their downstream writes failed:\n"
        "> - **Tasks** — mtl write failed\n"
        ">\n"
        "> Receipt: [[receipts/Faith-20260503-abc12345]]\n"
        "> The next scheduled run will retry these sections automatically.\n"
        "\n"
        "# Faith\n"
        "\n"
        "## Tasks\n"
        "\n"
        "- [ ] task one\n"
        "- [ ] task two\n"
    )
    receipt = bdi.build_receipt(
        source={
            "key": "00_Inbox/brain-dumps/Faith.md",
            "filename": "Faith.md",
            "content_hash": "sha256:abcd1234" + "0" * 56,
            "size_bytes": 100,
        },
        run={
            "workflow": "brain-dump-processor",
            "run_id": "run-1",
            "started_at": "2026-05-04T07:00:00Z",
            "finished_at": "2026-05-04T07:00:30Z",
            "executor": "python",
            "no_reset": False,
        },
        archive={
            "key": "99_System/archive/brain-dumps/2026-05-04/Faith.md",
            "etag": '"a1"',
            "size_bytes": 100,
            "verified": True,
        },
        sections=[
            {
                "section": "Tasks",
                "section_type": "tasks",
                "items_extracted": 2,
                "writes": [{"target": "mtl", "verified": True}],
                "verified": True,
            },
        ],
    )
    new_fm = {
        "domain": "faith",
        "area": "faith",
        "status": "extracted",
        "content_hash": "sha256:abcd1234" + "0" * 56,
        "last_checked": "2026-05-04T07:00:00Z",
        "last_processed": "2026-05-04T07:00:00Z",
        "last_processed_hash": "sha256:abcd1234" + "0" * 56,
        "last_receipt": "extraction-receipts/Faith-20260504-abcd1234.json",
        "last_partial_reasons": [],
    }

    def template_for(name: str) -> str:
        return "<!-- cleared template -->"

    out = bdi.apply_reset(
        content=content,
        receipt=receipt,
        new_frontmatter=new_fm,
        section_template_for=template_for,
    )

    assert "Retention notice" not in out
    assert "task one" not in out  # tasks section cleared
    assert "<!-- cleared template -->" in out


def test_apply_reset_partial_keeps_failed_sections_and_adds_retention_block():
    content = (
        "---\n"
        "domain: faith\n"
        "area: faith\n"
        "status: scanning\n"
        "---\n"
        "\n"
        "# Faith\n"
        "\n"
        "## Tasks\n"
        "\n"
        "- [ ] task one\n"
        "- [ ] task two\n"
        "\n"
        "## Articles\n"
        "\n"
        "- https://example.com/article\n"
    )
    receipt = bdi.build_receipt(
        source={
            "key": "00_Inbox/brain-dumps/Faith.md",
            "filename": "Faith.md",
            "content_hash": "sha256:abcd1234" + "0" * 56,
            "size_bytes": 100,
        },
        run={
            "workflow": "x",
            "run_id": "1",
            "started_at": "2026-05-04T07:00:00Z",
            "finished_at": "2026-05-04T07:00:30Z",
            "executor": "python",
            "no_reset": False,
        },
        archive={
            "key": "x",
            "etag": '"a"',
            "size_bytes": 100,
            "verified": True,
        },
        sections=[
            {
                "section": "Tasks",
                "section_type": "tasks",
                "items_extracted": 2,
                "writes": [{"target": "mtl", "verified": True}],
                "verified": True,
            },
            {
                "section": "Articles",
                "section_type": "articles",
                "items_extracted": 1,
                "writes": [{"target": "queue", "verified": False, "error": "503"}],
                "verified": False,
                "reason": "queue write failed (head_object 503)",
            },
        ],
    )
    new_fm = {
        "domain": "faith",
        "area": "faith",
        "status": "partial",
        "content_hash": "sha256:abcd1234" + "0" * 56,
        "last_checked": "2026-05-04T07:00:00Z",
        "last_processed": None,
        "last_processed_hash": None,
        "last_receipt": "extraction-receipts/Faith-20260504-abcd1234.json",
        "last_partial_reasons": [],
    }

    def template_for(name: str) -> str:
        if name == "Tasks":
            return "<!-- cleared -->"
        return None  # Articles is not verified — should not be consulted

    out = bdi.apply_reset(
        content=content,
        receipt=receipt,
        new_frontmatter=new_fm,
        section_template_for=template_for,
    )

    # Tasks cleared
    assert "task one" not in out
    assert "<!-- cleared -->" in out
    # Articles NOT cleared
    assert "https://example.com/article" in out
    # Retention block added with the failed-section reason
    assert "[!warning] Retention notice" in out
    assert "Articles" in out


# ── Receipt building ─────────────────────────────────────────────────────────

def test_build_receipt_extracted_when_archive_and_all_sections_verified():
    receipt = bdi.build_receipt(
        source={"key": "f", "filename": "f.md", "content_hash": "sha256:abcd", "size_bytes": 100},
        run={"workflow": "x", "run_id": "1", "started_at": "2026-05-04T07:00:00Z",
             "finished_at": "2026-05-04T07:00:30Z", "executor": "python", "no_reset": False},
        archive={"key": "x", "etag": '"a"', "size_bytes": 100, "verified": True},
        sections=[
            {"section": "S", "section_type": "tasks", "items_extracted": 1,
             "writes": [{"target": "mtl", "verified": True}], "verified": True},
        ],
    )
    s = receipt["summary"]
    assert s["all_sections_verified"] is True
    assert s["final_status"] == "extracted"
    assert s["reset_applied_count"] == 1


def test_build_receipt_partial_when_one_section_fails():
    receipt = bdi.build_receipt(
        source={"key": "f", "filename": "f.md", "content_hash": "sha256:abcd", "size_bytes": 100},
        run={"workflow": "x", "run_id": "1", "started_at": "2026-05-04T07:00:00Z",
             "finished_at": "2026-05-04T07:00:30Z", "executor": "python", "no_reset": False},
        archive={"key": "x", "etag": '"a"', "size_bytes": 100, "verified": True},
        sections=[
            {"section": "Tasks", "section_type": "tasks", "items_extracted": 3,
             "writes": [{"target": "mtl", "verified": True}], "verified": True},
            {"section": "Articles", "section_type": "articles", "items_extracted": 1,
             "writes": [{"target": "queue", "verified": False}], "verified": False},
        ],
    )
    s = receipt["summary"]
    assert s["all_sections_verified"] is False
    assert s["verified_sections"] == ["Tasks"]
    assert s["failed_sections"] == ["Articles"]
    assert s["final_status"] == "partial"
    assert s["reset_applied_count"] == 1


def test_build_receipt_error_when_archive_failed():
    receipt = bdi.build_receipt(
        source={"key": "f", "filename": "f.md", "content_hash": "sha256:abcd", "size_bytes": 100},
        run={"workflow": "x", "run_id": "1", "started_at": "2026-05-04T07:00:00Z",
             "finished_at": "2026-05-04T07:00:30Z", "executor": "python", "no_reset": False},
        archive={"key": "x", "etag": None, "size_bytes": 0, "verified": False},
        sections=[],
    )
    assert receipt["summary"]["final_status"] == "error"


def test_decide_final_status_returns_summary_value():
    receipt = bdi.build_receipt(
        source={"key": "f", "filename": "f.md", "content_hash": "sha256:abcd", "size_bytes": 100},
        run={"workflow": "x", "run_id": "1", "started_at": "2026-05-04T07:00:00Z",
             "finished_at": "2026-05-04T07:00:30Z", "executor": "python", "no_reset": False},
        archive={"key": "x", "etag": '"a"', "size_bytes": 100, "verified": True},
        sections=[
            {"section": "S", "section_type": "tasks", "items_extracted": 1,
             "writes": [{"target": "mtl", "verified": True}], "verified": True},
        ],
    )
    assert bdi.decide_final_status(receipt) == "extracted"


# ── State machine ────────────────────────────────────────────────────────────

def test_next_state_basic_transitions():
    assert bdi.next_state("empty", "edit_detected") == "has_content"
    assert bdi.next_state("has_content", "run_start") == "scanning"
    assert bdi.next_state("partial", "run_start") == "scanning"
    assert bdi.next_state("error", "run_start") == "scanning"
    assert bdi.next_state("scanning", "run_complete", all_verified=True) == "extracted"
    assert bdi.next_state("scanning", "run_complete", all_verified=False) == "partial"
    assert bdi.next_state("scanning", "pre_extraction_failure") == "error"
    assert bdi.next_state("extracted", "reset_applied") == "empty"


def test_next_state_unknown_event_or_state_is_noop():
    assert bdi.next_state("empty", "totally_made_up_event") == "empty"
    assert bdi.next_state("extracted", "edit_detected") == "extracted"  # wrong state
    assert bdi.next_state("scanning", "edit_detected") == "scanning"


# ── Frontmatter parse / serialize ────────────────────────────────────────────

def test_frontmatter_parse_serialize_roundtrip():
    content = (
        "---\n"
        "domain: faith\n"
        "area: faith\n"
        "status: empty\n"
        "content_hash: sha256:abc\n"
        "last_processed: null\n"
        "last_partial_reasons: []\n"
        "---\n"
        "\n"
        "# Body\n"
        "\n"
        "content\n"
    )
    fm, body = bdi.parse_frontmatter(content)
    assert fm["domain"] == "faith"
    assert fm["status"] == "empty"
    assert fm["last_processed"] is None
    assert fm["last_partial_reasons"] == []
    assert "# Body" in body

    # Roundtrip
    roundtripped = bdi.serialize_frontmatter(fm, body)
    fm2, body2 = bdi.parse_frontmatter(roundtripped)
    assert fm2 == fm


def test_parse_frontmatter_no_frontmatter_returns_empty_dict():
    content = "# Just a body\n\nNo frontmatter here.\n"
    fm, body = bdi.parse_frontmatter(content)
    assert fm == {}
    assert body == content


# ── Body emptiness ───────────────────────────────────────────────────────────

def test_is_body_effectively_empty_template_only():
    template = (
        "\n# Brain Dump — Faith\n\n"
        "> **How to use:** template instructions.\n\n"
        "## Quick Notes\n\n"
        "*Raw thoughts, observations*\n\n"
        "<!-- Add notes here -->\n\n"
        "---\n"
    )
    assert bdi.is_body_effectively_empty(template) is True


def test_is_body_effectively_empty_with_content_returns_false():
    body = (
        "\n# Brain Dump — Faith\n\n"
        "## Quick Notes\n\n"
        "I want to start a Bible study group.\n"
    )
    assert bdi.is_body_effectively_empty(body) is False


# ── Drift-prevention guardrails (added 2026-05-03 AMBER pass) ────────────────

def test_migration_round_trip_only_heartbeat_advances():
    """Running the migration twice on the same fm + body must produce
    identical output EXCEPT for `last_checked` (heartbeat semantic — allowed
    to advance on every run). Every other field must be byte-stable.

    This locks down the contract that migration is "idempotent in shape" so
    a future change that accidentally non-determinizes another field
    (e.g. UUID-based receipt paths, mutable defaults) fails CI.
    """
    fm = {
        "domain": "personal", "area": "personal", "status": "empty",
        "last_processed": "2026-04-20",  # legacy stale value
    }
    out1 = bdi.migrate_frontmatter(fm, SIMPLE_BODY, "2026-05-04T07:00:00Z")
    out2 = bdi.migrate_frontmatter(out1, SIMPLE_BODY, "2026-05-04T07:00:30Z")

    diffs = {k: (out1.get(k), out2.get(k))
             for k in (set(out1) | set(out2))
             if out1.get(k) != out2.get(k)}
    assert set(diffs.keys()) <= {"last_checked"}, (
        f"migration not idempotent — fields besides last_checked changed "
        f"between runs: {diffs}"
    )


def test_receipt_schema_version_pinned():
    """Pinning the receipt schema_version to 1 ensures any change requires
    a deliberate version bump + audit script update. Catches the case
    where someone bumps RECEIPT_SCHEMA_VERSION without updating the audit
    script's compatibility check.
    """
    assert bdi.RECEIPT_SCHEMA_VERSION == 1, (
        "RECEIPT_SCHEMA_VERSION changed — update audit_extraction_receipts.py "
        "schema-compatibility check before bumping."
    )
    sample = bdi.build_receipt(
        source={"key": "x", "filename": "x.md", "content_hash": "sha256:abcd", "size_bytes": 1},
        run={"workflow": "x", "run_id": "1", "started_at": "2026-05-04T07:00:00Z",
             "finished_at": "2026-05-04T07:00:30Z", "executor": "python", "no_reset": False},
        archive={"key": "x", "etag": '"a"', "size_bytes": 1, "verified": True},
        sections=[],
    )
    assert sample["schema_version"] == 1
