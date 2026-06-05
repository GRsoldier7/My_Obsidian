"""
tools/bd_integrity.py — Brain-dump pipeline integrity primitives.

Pure functions only; no I/O. The orchestrator (process_brain_dump.py, invoked
directly or through the OHO runner) is responsible for actual S3/MinIO calls.

This is the single logic kernel that both the Python processor and the
n8n workflow consume. Keeping this pure means: same input → same output
regardless of executor; trivially testable; cannot drift between Python
and JS because there is no JS implementation of this layer.

See docs/adr/0005-brain-dump-state-machine-and-receipts.md for the design.
"""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from datetime import datetime, timezone
from typing import Any, Callable, Optional

# ── Constants ────────────────────────────────────────────────────────────────

CANONICAL_FRONTMATTER_FIELDS: tuple[str, ...] = (
    "domain",
    "area",
    "status",
    "content_hash",
    "last_checked",
    "last_processed",
    "last_processed_hash",
    "last_receipt",
    "last_partial_reasons",
)

VALID_STATES: frozenset[str] = frozenset(
    {"empty", "has_content", "scanning", "extracted", "partial", "error"}
)
WORK_ELIGIBLE_STATES: frozenset[str] = frozenset({"has_content", "partial", "error"})

RECEIPT_SCHEMA_VERSION: int = 1
RECEIPTS_PREFIX: str = "99_System/extraction-receipts/"
ARCHIVE_PREFIX: str = "99_System/archive/brain-dumps/"

# Match an Obsidian callout retention block. The block ends at the next H1/H2
# heading or end-of-file. Callouts are line-prefixed with `> ` so we anchor on
# `^> [!warning] Retention notice` and stop at the first non-quoted line that
# starts a new section.
_RETENTION_BLOCK_RE = re.compile(
    r"^> \[!warning\] Retention notice.*?(?=\n(?:## |# |[^>\n]|\Z))",
    re.MULTILINE | re.DOTALL,
)


# ── Hashing + normalization ──────────────────────────────────────────────────

def _normalize_body(body: str) -> str:
    """Apply canonical normalization for hashing.

    1. Strip retention block (so adding/removing the block doesn't change hash)
    2. Unicode NFC
    3. Force LF line endings (so CRLF/CR don't change hash)
    """
    body = strip_retention_block(body)
    body = unicodedata.normalize("NFC", body)
    body = body.replace("\r\n", "\n").replace("\r", "\n")
    return body


def compute_content_hash(body: str) -> str:
    """Compute sha256 of the normalized body. Returns 'sha256:<hex>'."""
    normalized = _normalize_body(body)
    h = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    return f"sha256:{h}"


def strip_retention_block(content: str) -> str:
    """Remove any retention-notice callout from content. Idempotent."""
    return _RETENTION_BLOCK_RE.sub("", content)


# ── Frontmatter parse + serialize ────────────────────────────────────────────

_YAML_FENCE_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?", re.DOTALL)


def parse_frontmatter(content: str) -> tuple[dict[str, Any], str]:
    """Split frontmatter and body. Returns (fm_dict, body).

    Handles only the canonical OHO frontmatter shape: single-line scalars,
    inline JSON-style lists, no nested mappings. Unknown fields are
    preserved as raw strings for forward-compat.
    """
    m = _YAML_FENCE_RE.match(content)
    if not m:
        return {}, content
    raw_fm = m.group(1)
    body = content[m.end():]
    fm: dict[str, Any] = {}
    for line in raw_fm.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if ":" not in line:
            continue
        k, _, v = line.partition(":")
        k = k.strip()
        v = v.strip()
        if v.startswith('"') and v.endswith('"') and len(v) >= 2:
            v = v[1:-1]
        elif v.startswith("'") and v.endswith("'") and len(v) >= 2:
            v = v[1:-1]
        if v == "[]":
            fm[k] = []
        elif v == "null" or v == "~" or v == "":
            fm[k] = None
        else:
            fm[k] = v
    return fm, body


def _yaml_value(v: Any) -> str:
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, list):
        return json.dumps(v) if v else "[]"
    return str(v)


def serialize_frontmatter(fm: dict[str, Any], body: str) -> str:
    """Render frontmatter dict back to YAML in canonical order.

    Unknown keys preserved at the end (after canonical keys).
    """
    lines = ["---"]
    seen: set[str] = set()
    for k in CANONICAL_FRONTMATTER_FIELDS:
        if k in fm:
            lines.append(f"{k}: {_yaml_value(fm[k])}")
            seen.add(k)
    for k, v in fm.items():
        if k not in seen:
            lines.append(f"{k}: {_yaml_value(v)}")
    lines.append("---")
    head = "\n".join(lines) + "\n"
    if body.startswith("\n"):
        return head + body[1:] if body[1:2] != "\n" else head + body
    return head + body


# ── Body emptiness detection ─────────────────────────────────────────────────

def is_body_effectively_empty(body: str) -> bool:
    """True if body has no real user content (only template scaffolding).

    Mirrors `is_section_empty` from process_brain_dump.py exactly so the
    migration script and the live processor agree on what's "empty."
    Strips:
      - retention blocks (added by partial-state runs)
      - HTML comments
      - blockquote lines (instruction callouts like "> How to use:")
      - italic-only lines (template placeholders like `*Raw thoughts...*`)
      - horizontal rules
      - headings (H1-H6)
      - Obsidian inline-field placeholders (`=this.field`)
      - tag-reference lines (`*Tags: ...*`)
      - format-example lines (anything containing `Format:`)
    """
    stripped = strip_retention_block(body)
    stripped = re.sub(r"<!--.*?-->", "", stripped, flags=re.DOTALL)
    stripped = re.sub(r"^>.*$", "", stripped, flags=re.MULTILINE)
    stripped = re.sub(r"^\s*\*[^*\n]+\*\s*$", "", stripped, flags=re.MULTILINE)
    stripped = re.sub(r"^[-*_]{3,}$", "", stripped, flags=re.MULTILINE)
    stripped = re.sub(r"^#+\s.*$", "", stripped, flags=re.MULTILINE)
    stripped = re.sub(r"^\s*=this\.\w+\s*$", "", stripped, flags=re.MULTILINE)
    stripped = re.sub(r"^\s*\*Tags:.*\*\s*$", "", stripped, flags=re.MULTILINE)
    stripped = re.sub(r"^.*\bFormat:.*$", "", stripped, flags=re.MULTILINE)
    return not stripped.strip()


# ── Path helpers ─────────────────────────────────────────────────────────────

_SLUG_NORMALIZE_RE = re.compile(r"[\s—–]+")
_SLUG_DEDUP_RE = re.compile(r"-+")


def slug_for_filename(filename: str) -> str:
    """Canonical filename → receipt-stem normalizer.

    Strip ``.md``, collapse any run of whitespace and em/en dashes to a single
    ``-``, dedup repeated hyphens, and trim leading/trailing hyphens. This is
    the *single source of truth* for the stem embedded in a receipt key —
    anyone who needs to derive a receipt-stem from a filename (the live
    processor, the audit, future tooling) MUST use this function so the
    derivations stay in sync.
    """
    stem = filename
    if stem.endswith(".md"):
        stem = stem[:-3]
    stem = _SLUG_NORMALIZE_RE.sub("-", stem)
    stem = _SLUG_DEDUP_RE.sub("-", stem).strip("-")
    return stem


# Backward-compat alias for any external caller that imported the private name.
_slug_for_filename = slug_for_filename


def receipt_path(source_filename: str, date_yyyymmdd: str, content_hash: str) -> str:
    """Compute the canonical receipt key.

    Format: 99_System/extraction-receipts/<stem>-<YYYYMMDD>-<sha8>.json

    `<sha8>` is the first 8 hex chars of `content_hash` (after the `sha256:`
    prefix). This makes the receipt path content-addressed: same content →
    same receipt path; idempotent re-runs overwrite in place.
    """
    if ":" in content_hash:
        sha = content_hash.split(":", 1)[1]
    else:
        sha = content_hash
    sha8 = sha[:8]
    stem = _slug_for_filename(source_filename)
    return f"{RECEIPTS_PREFIX}{stem}-{date_yyyymmdd}-{sha8}.json"


def archive_path(source_filename: str, date_yyyymmdd: str) -> str:
    """Compute the canonical archive key (raw source, untouched)."""
    yyyy = date_yyyymmdd[:4]
    mm = date_yyyymmdd[4:6]
    dd = date_yyyymmdd[6:8]
    return f"{ARCHIVE_PREFIX}{yyyy}-{mm}-{dd}/{source_filename}"


# ── Receipt building ─────────────────────────────────────────────────────────

def compute_summary(sections: list[dict[str, Any]], archive_verified: bool) -> dict[str, Any]:
    """Compute receipt summary fields purely from section + archive state."""
    verified = [s["section"] for s in sections if s.get("verified")]
    failed = [s["section"] for s in sections if not s.get("verified")]
    all_verified = bool(sections) and not failed

    if not archive_verified:
        final = "error"
    elif all_verified:
        final = "extracted"
    else:
        final = "partial"

    return {
        "all_sections_verified": all_verified,
        "verified_sections": verified,
        "failed_sections": failed,
        "reset_applied_count": len(verified),
        "final_status": final,
    }


def build_receipt(
    *,
    source: dict[str, Any],
    run: dict[str, Any],
    archive: dict[str, Any],
    sections: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build the canonical receipt JSON. Computes summary from inputs."""
    summary = compute_summary(sections, archive_verified=bool(archive.get("verified")))
    return {
        "schema_version": RECEIPT_SCHEMA_VERSION,
        "source": source,
        "run": run,
        "archive": archive,
        "sections": sections,
        "summary": summary,
    }


def decide_final_status(receipt: dict[str, Any]) -> str:
    return receipt["summary"]["final_status"]


# ── Retention block ──────────────────────────────────────────────────────────

def make_retention_block(
    date_iso_or_yyyymmdd: str,
    failed_sections: list[dict[str, Any]],
    receipt_key: str,
) -> str:
    """Render an Obsidian callout retention notice for partial-state files."""
    date_display = date_iso_or_yyyymmdd[:10] if "-" in date_iso_or_yyyymmdd else \
        f"{date_iso_or_yyyymmdd[:4]}-{date_iso_or_yyyymmdd[4:6]}-{date_iso_or_yyyymmdd[6:8]}"

    lines = [
        f"> [!warning] Retention notice — {date_display}",
        "> The following sections were NOT cleared because their downstream writes failed:",
    ]
    for fs in failed_sections:
        section = fs.get("section", "?")
        reason = fs.get("reason", "unknown")
        lines.append(f"> - **{section}** — {reason}")
    lines.append(">")
    # Wikilink: drop trailing .json so Obsidian resolves the note.
    wiki = receipt_key
    if wiki.endswith(".json"):
        wiki = wiki[:-5]
    lines.append(f"> Receipt: [[{wiki}]]")
    lines.append("> The next scheduled run will retry these sections automatically.")
    return "\n".join(lines)


# ── Frontmatter migration ────────────────────────────────────────────────────

def migrate_frontmatter(
    fm: dict[str, Any],
    body: str,
    now_iso: str,
) -> dict[str, Any]:
    """Transform legacy frontmatter into the canonical 8-field schema. Idempotent.

    - Computes content_hash from current normalized body.
    - Sets last_checked to now (heartbeat).
    - Determines status from body emptiness.
    - For empty bodies: sets last_processed_hash to current_hash so the file
      isn't picked up as "edited since last processed" until user actually edits.
    - Preserves any unknown legacy fields (forward-compat).
    """
    new_fm: dict[str, Any] = dict(fm)  # preserve unknown fields

    new_fm["content_hash"] = compute_content_hash(body)
    new_fm["last_checked"] = now_iso

    if "last_partial_reasons" not in new_fm or new_fm.get("last_partial_reasons") is None:
        new_fm["last_partial_reasons"] = []
    if "last_receipt" not in new_fm:
        new_fm["last_receipt"] = None

    body_empty = is_body_effectively_empty(body)

    if body_empty:
        new_fm["status"] = "empty"
        new_fm.setdefault("last_processed_hash", new_fm["content_hash"])
        new_fm.setdefault("last_processed", now_iso)
    else:
        # has_content explicitly means "not yet processed under the new gates."
        # Force-clear any stale last_processed/_hash from the legacy schema —
        # otherwise the audit + downstream readers see contradictory state
        # (last_processed set but last_processed_hash null).
        new_fm["status"] = "has_content"
        new_fm["last_processed_hash"] = None
        new_fm["last_processed"] = None

    new_fm.setdefault("domain", "personal")
    new_fm.setdefault("area", "personal")

    return new_fm


# ── State machine ────────────────────────────────────────────────────────────

def next_state(
    current: str,
    event: str,
    *,
    all_verified: Optional[bool] = None,
) -> str:
    """Compute next state from current + event. Returns the new state.

    Events:
      - 'edit_detected'         : empty → has_content
      - 'run_start'             : empty/has_content/partial/error → scanning
      - 'run_complete'          : scanning + all_verified=True  → extracted
                                : scanning + all_verified=False → partial
      - 'pre_extraction_failure': scanning → error
      - 'reset_applied'         : extracted → empty
    Unknown event/state combinations no-op (return current).
    """
    if event == "edit_detected" and current == "empty":
        return "has_content"
    if event == "run_start" and current in (WORK_ELIGIBLE_STATES | {"empty"}):
        return "scanning"
    if event == "run_complete" and current == "scanning":
        return "extracted" if all_verified else "partial"
    if event == "pre_extraction_failure" and current == "scanning":
        return "error"
    if event == "reset_applied" and current == "extracted":
        return "empty"
    return current


# ── Reset application ────────────────────────────────────────────────────────

def _replace_section_body(body: str, header: str, template: str) -> str:
    """Replace the body of `## <header>` with `template`. Until next H2 / EOF."""
    pattern = rf"(## {re.escape(header)}\n).*?(?=\n## |\Z)"
    replacement = rf"\g<1>\n{template}\n"
    return re.sub(pattern, replacement, body, count=1, flags=re.DOTALL)


def apply_reset(
    *,
    content: str,
    receipt: dict[str, Any],
    new_frontmatter: dict[str, Any],
    section_template_for: Callable[[str], Optional[str]],
) -> str:
    """Apply the gated reset to file content. Pure transform.

    - Frontmatter is replaced with new_frontmatter.
    - Verified sections (per receipt) are replaced with their template body.
    - Failed sections are kept as-is; a retention block is prepended.
    - Existing retention block is stripped first (a re-run that succeeds clears it).
    """
    summary = receipt["summary"]
    sections = receipt["sections"]
    verified_section_names = set(summary["verified_sections"])

    _, body = parse_frontmatter(content)
    body = strip_retention_block(body).strip("\n")

    for section in sections:
        name = section["section"]
        if name not in verified_section_names:
            continue
        template = section_template_for(name)
        if template is None:
            continue
        body = _replace_section_body(body, name, template)

    failed = [s for s in sections if not s.get("verified")]
    if failed:
        date_iso = receipt["run"]["started_at"]
        date_yyyymmdd = date_iso[:10].replace("-", "")
        rk = receipt_path(
            receipt["source"]["filename"],
            date_yyyymmdd,
            receipt["source"]["content_hash"],
        )
        retention = make_retention_block(date_iso, failed, rk)
        body = retention + "\n\n" + body.lstrip("\n")

    return serialize_frontmatter(new_frontmatter, body if body.startswith("\n") else "\n" + body)


# ── Time helper ──────────────────────────────────────────────────────────────

def now_utc_iso() -> str:
    """ISO-8601 UTC timestamp. Centralized so tests can monkey-patch if needed."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
