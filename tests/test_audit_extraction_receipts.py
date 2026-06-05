"""Regression: audit's R1 receipt-stem derivation must match the canonical key.

The audit had an em-dash bug: ``" — "`` (space + em-dash + space) collapsed
to ``"--"`` (two hyphens) in the audit's stem, but the receipt path actually
written by ``bd_integrity.receipt_path()`` collapses the same run to a single
hyphen. The substring search in R1 then missed live receipts and emitted
spurious "no receipt found" findings.

This regression test pins the contract on three levels:
  1. Hard literal — the operator's reported case: ``BrainDump — Home.md``
     resolves to ``BrainDump-Home``, not ``BrainDump--Home``.
  2. Audit derivation agrees with ``bd_integrity.slug_for_filename`` for
     every brain-dump filename the live processor actually writes.
  3. R1's substring search succeeds against the canonical receipt key.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import audit_extraction_receipts as aer  # noqa: E402
from tools import bd_integrity as bdi  # noqa: E402


# Filenames the production processor actually writes brain-dump receipts for.
# The em-dash and the surrounding spaces are intentional — they are the bug
# trigger and must be preserved verbatim.
PROD_FILENAMES: list[str] = [
    "BrainDump — Home.md",
    "BrainDump — Personal.md",
    "BrainDump — Faith.md",
    "BrainDump — Family.md",
    "BrainDump — Health.md",
    "BrainDump — Business (Echelon Seven).md",
    "BrainDump — Work (Parallon).md",
    "BrainDump — Consulting.md",
    "Bible post on Social Media.md",
    "Coding.md",
    "Website & Business.md",
    "Faith.md",
]


def test_brain_dump_home_resolves_to_single_hyphen_stem():
    """Hard literal: BrainDump — Home.md → BrainDump-Home, not BrainDump--Home.

    This is the exact case the operator reported. Pinned as a literal so it
    can never silently re-regress.
    """
    derived = aer._stem_for_runlog_entry("BrainDump — Home.md")
    assert derived == "BrainDump-Home", (
        f"expected single-hyphen stem 'BrainDump-Home'; got {derived!r}"
    )
    assert "--" not in derived, (
        f"audit produced double-hyphen — em-dash collapsing is broken "
        f"(derived={derived!r})"
    )


@pytest.mark.parametrize("filename", PROD_FILENAMES)
def test_audit_stem_agrees_with_canonical_slug(filename):
    """The audit's stem must equal ``bd_integrity.slug_for_filename(filename)``.

    Both functions are deriving the same thing — the slug used inside the
    receipt key — so they must agree. Any divergence is a contract bug.
    """
    canonical = bdi.slug_for_filename(filename)
    derived = aer._stem_for_runlog_entry(filename)
    assert derived == canonical, (
        f"audit derived {derived!r}; bd_integrity canonical is {canonical!r} "
        f"(filename: {filename!r})"
    )


@pytest.mark.parametrize("filename", PROD_FILENAMES)
def test_audit_stem_is_substring_of_canonical_receipt_key(filename):
    """Tightest contract: derived stem must satisfy R1's substring search.

    R1 does ``stem in receipt_key``. If that ever fails, the audit emits
    spurious "no receipt found" findings against healthy data — the exact
    bug the operator hit on 2026-05-04.
    """
    receipt_key = bdi.receipt_path(filename, "20260504",
                                   "sha256:" + "a" * 64)
    derived = aer._stem_for_runlog_entry(filename)
    assert derived in receipt_key, (
        f"audit's substring search would miss the receipt: "
        f"derived={derived!r} not in {receipt_key!r}"
    )
