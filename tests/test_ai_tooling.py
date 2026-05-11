from __future__ import annotations

import importlib.util
import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_audit_module():
    script = REPO_ROOT / "scripts" / "audit_ai_tooling.py"
    spec = importlib.util.spec_from_file_location("audit_ai_tooling", script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_ai_tooling_surface_files_exist():
    required = [
        "AGENTS.md",
        "docs/AI_TOOLING.md",
        ".mcp.example.json",
        "scripts/audit_ai_tooling.py",
    ]
    missing = [path for path in required if not (REPO_ROOT / path).exists()]
    assert not missing, "Missing AI tooling files: " + ", ".join(missing)


def test_mcp_example_is_valid_json_and_has_no_secret_literals():
    config_path = REPO_ROOT / ".mcp.example.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))

    assert "mcpServers" in config
    assert {"context7", "playwright", "memory"}.issubset(config["mcpServers"])

    raw = config_path.read_text(encoding="utf-8")
    forbidden_literals = [
        "sk-or-",
        "xoxb-",
        "AKIA",
        "AIza",
        "ghp_",
        "github_pat_",
        "MINIO_SECRET_KEY=",
        "OPENROUTER_API_KEY=",
    ]
    found = [literal for literal in forbidden_literals if literal in raw]
    assert not found, "MCP example contains secret-looking literals: " + ", ".join(found)


def test_ai_tooling_audit_passes():
    audit = _load_audit_module()
    findings = audit.run_audit(REPO_ROOT)
    assert findings == []
