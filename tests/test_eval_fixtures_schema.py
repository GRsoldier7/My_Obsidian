"""Schema validation for evals/comms_privacy/ fixture set (ADR-0008 §15).

Every fixture file MUST:
  - parse as valid JSON
  - carry the required top-level fields
  - declare a class in {public, private, sensitive}
  - declare egress verdicts for all 5 peers
  - have an `id` matching its filename's numeric prefix

These checks land BEFORE tools/privacy_classifier.py ships so the fixture set
is already a frozen contract by the time the classifier reads it.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = REPO_ROOT / "evals" / "comms_privacy"

REQUIRED_KEYS = {"id", "class", "category", "payload", "hints", "expected_reasons", "expected_egress"}
ALLOWED_CLASSES = {"public", "private", "sensitive"}
REQUIRED_PEERS = {"to_lxc", "to_desktop", "to_vps", "to_broker", "to_openrouter"}
ID_FROM_FILENAME = re.compile(r"^F-(\d{4})-[a-z0-9-]+\.json$")
ID_IN_FIXTURE = re.compile(r"^F-(\d{4})$")


def _fixture_files() -> list[Path]:
    return sorted(p for p in FIXTURE_DIR.glob("F-*.json") if p.is_file())


def test_fixture_dir_has_fixtures():
    assert _fixture_files(), f"No fixtures found under {FIXTURE_DIR}"


@pytest.mark.parametrize("path", _fixture_files(), ids=lambda p: p.name)
def test_fixture_parses_as_json(path: Path):
    json.loads(path.read_text(encoding="utf-8"))


@pytest.mark.parametrize("path", _fixture_files(), ids=lambda p: p.name)
def test_fixture_has_required_keys(path: Path):
    doc = json.loads(path.read_text(encoding="utf-8"))
    missing = REQUIRED_KEYS - set(doc.keys())
    assert not missing, f"{path.name} missing keys: {missing}"


@pytest.mark.parametrize("path", _fixture_files(), ids=lambda p: p.name)
def test_fixture_class_is_canonical(path: Path):
    doc = json.loads(path.read_text(encoding="utf-8"))
    assert doc["class"] in ALLOWED_CLASSES, f"{path.name} has class={doc['class']!r}"


@pytest.mark.parametrize("path", _fixture_files(), ids=lambda p: p.name)
def test_fixture_egress_covers_all_peers(path: Path):
    doc = json.loads(path.read_text(encoding="utf-8"))
    eg = doc["expected_egress"]
    missing = REQUIRED_PEERS - set(eg.keys())
    assert not missing, f"{path.name} missing egress for: {missing}"


@pytest.mark.parametrize("path", _fixture_files(), ids=lambda p: p.name)
def test_fixture_id_matches_filename(path: Path):
    doc = json.loads(path.read_text(encoding="utf-8"))
    fname_match = ID_FROM_FILENAME.match(path.name)
    assert fname_match, f"Filename doesn't match `F-NNNN-slug.json`: {path.name}"
    id_match = ID_IN_FIXTURE.match(doc["id"])
    assert id_match, f"Fixture `id` doesn't match `F-NNNN`: {doc['id']!r}"
    assert fname_match.group(1) == id_match.group(1), (
        f"{path.name}: filename id={fname_match.group(1)} but fixture id={id_match.group(1)}"
    )


@pytest.mark.parametrize("path", _fixture_files(), ids=lambda p: p.name)
def test_fixture_id_class_range_matches_class(path: Path):
    """Convention from README: 0001-0050 public, 0051-0100 private, 0101-0150 sensitive,
    0151-0200 edge-case (any class allowed)."""
    doc = json.loads(path.read_text(encoding="utf-8"))
    n = int(ID_IN_FIXTURE.match(doc["id"]).group(1))  # type: ignore[union-attr]
    cls = doc["class"]
    if 1 <= n <= 50:
        assert cls == "public", f"F-{n:04d} should be public, declares {cls}"
    elif 51 <= n <= 100:
        assert cls == "private", f"F-{n:04d} should be private, declares {cls}"
    elif 101 <= n <= 150:
        assert cls == "sensitive", f"F-{n:04d} should be sensitive, declares {cls}"
    elif 151 <= n <= 200:
        pass  # edge-case range allows any class
    else:
        pytest.fail(f"F-{n:04d} out of range (1-200)")


def test_fixture_ids_are_unique():
    seen: dict[str, Path] = {}
    for path in _fixture_files():
        doc = json.loads(path.read_text(encoding="utf-8"))
        if doc["id"] in seen:
            pytest.fail(f"Duplicate fixture id {doc['id']}: {path.name} and {seen[doc['id']].name}")
        seen[doc["id"]] = path
