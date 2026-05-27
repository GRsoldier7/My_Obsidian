"""
tools/task_id.py — stable task IDs for ADR-0009 (Threaded Tasks).

Format: ``t-YYYYwNN-XXXX`` where:
  - YYYY = ISO-year of creation (matches `%G`, which is ISO-year-aware)
  - NN   = ISO-week (matches `%V`, 1-53)
  - XXXX = first 4 chars of sha256(area + description + created_at_iso) in
           lowercase hex, giving 4 * 4 = 16 bits of entropy. At realistic OHO
           volume (~50 tasks/week) collisions are rare; the audit's per-week
           uniqueness scan catches them, and on collision the writer extends to
           5 chars and re-generates.

This module is the canonical source. The migration tool, the audit script, the
backing-file writer, and the runner endpoints all import from here.

PHASE STATUS: SKELETON. Phase C kickoff is post-soak (Mon 2026-05-18+).
This file is on the isolated `feature/phase-c-f-skeletons` branch until merge.
Tests pin the contract; implementation can evolve without breaking them.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime, timezone

# Lowercase hex: 4 chars = 16 bits. Plenty at OHO volume.
_ID_RE = re.compile(r"^t-(\d{4})w(\d{2})-([a-f0-9]{4,8})$")
DEFAULT_HASH_LEN = 4


@dataclass(frozen=True)
class TaskId:
    raw: str
    year: int
    week: int
    hash_part: str

    @property
    def week_anchor(self) -> str:
        return f"{self.year}w{self.week:02d}"


def generate_task_id(
    area: str,
    description: str,
    created_at: datetime | None = None,
    *,
    hash_len: int = DEFAULT_HASH_LEN,
) -> str:
    """Build the stable ID for a freshly-extracted task.

    Args:
        area: One of the 8 canonical OHO areas (faith / family / business /
              consulting / work / health / home / personal). Not validated here —
              the writer / audit enforces it.
        description: The MTL line's description text (everything before the first
                     ``[`` inline-field). Trim before passing.
        created_at: Timezone-aware datetime. Defaults to ``datetime.now(timezone.utc)``.
        hash_len: Number of trailing hex chars. 4 by default; extend to 5-8 on
                  collision per the audit's escalation rule.

    Returns:
        The ``t-YYYYwNN-XXXX`` ID string.

    Raises:
        ValueError if hash_len < 4 or > 8.
    """
    if hash_len < 4 or hash_len > 8:
        raise ValueError(f"hash_len must be in [4, 8], got {hash_len}")
    ts = created_at or datetime.now(timezone.utc)
    if ts.tzinfo is None:
        raise ValueError("created_at must be timezone-aware")
    iso_year, iso_week, _ = ts.isocalendar()
    desc_norm = " ".join(description.split())  # collapse whitespace, no trailing
    digest = hashlib.sha256(
        f"{area}\x00{desc_norm}\x00{ts.isoformat()}".encode("utf-8")
    ).hexdigest()
    hash_part = digest[:hash_len]
    return f"t-{iso_year}w{iso_week:02d}-{hash_part}"


def parse_task_id(raw: str) -> TaskId | None:
    """Return a TaskId for a valid string, None otherwise. Tolerant of 4-8 char hashes."""
    m = _ID_RE.match(raw)
    if not m:
        return None
    return TaskId(
        raw=raw,
        year=int(m.group(1)),
        week=int(m.group(2)),
        hash_part=m.group(3),
    )


def is_valid_task_id(raw: str) -> bool:
    return _ID_RE.match(raw) is not None


def collides(new_id: str, existing_ids: set[str]) -> bool:
    """True iff the new ID is already in use within the SAME week-anchor.

    The audit calls this for every new ID at write time. On True, the writer
    escalates ``hash_len`` by 1 and retries. After 4 escalations (4→5→6→7→8),
    if it still collides, that's a hash crisis — surface to the operator.
    """
    parsed_new = parse_task_id(new_id)
    if not parsed_new:
        return False
    if new_id in existing_ids:
        return True
    return False


def derive_backing_file_path(task_id: str, area: str) -> str:
    """The vault-relative path for the task's backing markdown file.

    Per ADR-0009: ``30_Tasks/<area>/<task_id>.md``. No vault prefix; MinIO key
    is rooted at bucket root.
    """
    if not is_valid_task_id(task_id):
        raise ValueError(f"not a valid task id: {task_id!r}")
    if not area or "/" in area or area.startswith("."):
        raise ValueError(f"invalid area: {area!r}")
    return f"30_Tasks/{area}/{task_id}.md"
