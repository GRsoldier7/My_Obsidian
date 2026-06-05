#!/usr/bin/env python3
"""
Audit the project-local AI tooling surface.

This checks the files that keep Skills, MCPs, and agent instructions aligned
across Claude, Codex, and future MCP-enabled agents.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]

REQUIRED_FILES = [
    "AGENTS.md",
    "docs/AI_TOOLING.md",
    ".mcp.example.json",
    "scripts/audit_ai_tooling.py",
    "scripts/sync_foundation_skills.sh",
]

AGENTS_REQUIRED_SNIPPETS = [
    "Never use a `Homelab/` prefix",
    "canonical Obsidian task format",
    "set -a && source .env && set +a",
    "Never hardcode secrets",
    "P1 is open",
    "docs/AI_TOOLING.md",
]

TOOLING_REQUIRED_SECTIONS = [
    "## User-Level Shared MCPs",
    "## Project-Local MCP Examples",
    "## Project-Local Skills",
    "## Deferred Or Rejected",
    "## Activation Matrix",
    "## Verification Commands",
]

REQUIRED_MCP_SERVERS = {
    "context7",
    "playwright",
    "memory",
    "sequential-thinking",
    "filesystem-oho",
    "bitwarden",
    "postgres-n8n-readonly",
}

FORBIDDEN_SECRET_PATTERNS = {
    "OpenRouter key": re.compile(r"sk-or-[A-Za-z0-9_-]{8,}"),
    "GitHub classic PAT": re.compile(r"ghp_[A-Za-z0-9_]{8,}"),
    "GitHub fine-grained PAT": re.compile(r"github_pat_[A-Za-z0-9_]{8,}"),
    "Slack token": re.compile(r"xox[baprs]-[A-Za-z0-9-]{8,}"),
    "AWS access key": re.compile(r"AKIA[0-9A-Z]{16}"),
    "Google API key": re.compile(r"AIza[0-9A-Za-z_-]{20,}"),
}


def _read(repo_root: Path, relative_path: str) -> str:
    return (repo_root / relative_path).read_text(encoding="utf-8")


def _audit_required_files(repo_root: Path, findings: list[str]) -> None:
    for relative_path in REQUIRED_FILES:
        if not (repo_root / relative_path).exists():
            findings.append(f"Missing required AI tooling file: {relative_path}")


def _audit_agents_md(repo_root: Path, findings: list[str]) -> None:
    text = _read(repo_root, "AGENTS.md")
    for snippet in AGENTS_REQUIRED_SNIPPETS:
        if snippet not in text:
            findings.append(f"AGENTS.md missing required guidance: {snippet}")


def _audit_ai_tooling_doc(repo_root: Path, findings: list[str]) -> None:
    text = _read(repo_root, "docs/AI_TOOLING.md")
    for section in TOOLING_REQUIRED_SECTIONS:
        if section not in text:
            findings.append(f"docs/AI_TOOLING.md missing section: {section}")


def _audit_mcp_example(repo_root: Path, findings: list[str]) -> None:
    path = repo_root / ".mcp.example.json"
    try:
        raw = path.read_text(encoding="utf-8")
        config = json.loads(raw)
    except json.JSONDecodeError as exc:
        findings.append(f".mcp.example.json is invalid JSON: {exc}")
        return

    servers = config.get("mcpServers")
    if not isinstance(servers, dict):
        findings.append(".mcp.example.json must contain an mcpServers object")
        return

    missing = sorted(REQUIRED_MCP_SERVERS - set(servers))
    if missing:
        findings.append(".mcp.example.json missing MCP servers: " + ", ".join(missing))

    for name, pattern in FORBIDDEN_SECRET_PATTERNS.items():
        if pattern.search(raw):
            findings.append(f".mcp.example.json contains secret-looking value: {name}")

    for server_name, server in servers.items():
        if not isinstance(server, dict):
            findings.append(f"{server_name} MCP config must be an object")
            continue
        command = server.get("command")
        args = server.get("args")
        if not command or not isinstance(args, list):
            findings.append(f"{server_name} MCP config needs command and args list")


def _audit_gitignore(repo_root: Path, findings: list[str]) -> None:
    text = _read(repo_root, ".gitignore")
    for snippet in [".mcp.json", ".memory/"]:
        if snippet not in text:
            findings.append(f".gitignore missing local AI tooling ignore: {snippet}")


def _audit_makefile(repo_root: Path, findings: list[str]) -> None:
    text = _read(repo_root, "Makefile")
    for snippet in ["audit-ai-tooling", "scripts/audit_ai_tooling.py"]:
        if snippet not in text:
            findings.append(f"Makefile missing AI tooling target detail: {snippet}")


def run_audit(repo_root: Path = REPO_ROOT) -> list[str]:
    repo_root = Path(repo_root)
    findings: list[str] = []

    _audit_required_files(repo_root, findings)
    if findings:
        return findings

    _audit_agents_md(repo_root, findings)
    _audit_ai_tooling_doc(repo_root, findings)
    _audit_mcp_example(repo_root, findings)
    _audit_gitignore(repo_root, findings)
    _audit_makefile(repo_root, findings)

    return findings


def main() -> int:
    findings = run_audit(REPO_ROOT)
    if findings:
        print("AI tooling audit failed:")
        for finding in findings:
            print(f"  - {finding}")
        return 1

    print("AI tooling audit passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
