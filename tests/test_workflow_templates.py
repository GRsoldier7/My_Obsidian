from __future__ import annotations

import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_DIR = REPO_ROOT / "workflows" / "n8n"
SETUP_SCRIPT = (REPO_ROOT / "scripts" / "setup-n8n.sh").read_text()


def iter_targets(connection_block: object) -> list[str]:
    targets: list[str] = []
    if not isinstance(connection_block, dict):
        return targets
    for branches in connection_block.values():
        if not isinstance(branches, list):
            continue
        for branch in branches:
            if not isinstance(branch, list):
                continue
            for item in branch:
                if isinstance(item, dict) and item.get("node"):
                    targets.append(str(item["node"]))
    return targets


def test_email_nodes_do_not_feed_log_nodes():
    violations: list[str] = []

    for workflow_path in sorted(WORKFLOW_DIR.glob("*.json")):
        workflow = json.loads(workflow_path.read_text())
        for source_name, connection_block in workflow.get("connections", {}).items():
            if not str(source_name).startswith("Email:"):
                continue
            for target_name in iter_targets(connection_block):
                if "log" in target_name.lower():
                    violations.append(
                        f"{workflow_path.name}: '{source_name}' -> '{target_name}'"
                    )

    assert not violations, "Email nodes must not feed log nodes:\n" + "\n".join(violations)


def test_setup_n8n_does_not_swallow_workflow_import_failures():
    assert "|| echo '{}'" not in SETUP_SCRIPT
    assert "ERROR: Failed to import" in SETUP_SCRIPT
    assert "ERROR: Import returned no workflow id" in SETUP_SCRIPT
    assert "ERROR: Failed to update" in SETUP_SCRIPT
    assert "ERROR: Failed to activate" in SETUP_SCRIPT
