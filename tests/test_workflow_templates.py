from __future__ import annotations

import json
import re
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_DIR = REPO_ROOT / "workflows" / "n8n"
SETUP_SCRIPT = (REPO_ROOT / "scripts" / "setup-n8n.sh").read_text(encoding="utf-8")

GLOBAL_ERROR_WF_ID = "jIOFmhr37mXEhlHz"

SCHEDULED_WORKFLOWS = [
    "article-processor.json",
    "brain-dump-processor-v2.json",
    "daily-note-creator-v2.json",
    "job-search-pipeline.json",
    "link-enricher.json",
    "live-dashboard-updater.json",
    "morning-briefing.json",
    "overdue-task-alert-v2.json",
    "system-health-monitor.json",
    "vault-health-report.json",
    "weekend-planner.json",
    "weekly-digest-v2.json",
]

ALLOWED_SKIP_REASONS = {
    "source_prefix_empty",
    "minio_offline",
    "minio_auth_error",
    "minio_list_failed",
    "queue_missing",
    "queue_empty",
    "no_new_items",
}


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
        workflow = json.loads(workflow_path.read_text(encoding="utf-8"))
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


def _load(name: str) -> dict:
    return json.loads((WORKFLOW_DIR / name).read_text(encoding="utf-8"))


def _cron_minutes(workflow: dict) -> int | None:
    """Return the first scheduleTrigger cron's (hour*60 + minute) in UTC, or None."""
    for node in workflow.get("nodes", []):
        if node.get("type") != "n8n-nodes-base.scheduleTrigger":
            continue
        for iv in node.get("parameters", {}).get("rule", {}).get("interval", []):
            expr = iv.get("expression")
            if expr:
                parts = expr.split()
                if len(parts) >= 2:
                    minute = int(parts[0]) if parts[0].isdigit() else 0
                    hour = int(parts[1]) if parts[1].isdigit() else 0
                    return hour * 60 + minute
    return None


@pytest.mark.parametrize("wf_name", SCHEDULED_WORKFLOWS)
def test_scheduled_workflows_wire_error_workflow(wf_name):
    wf = _load(wf_name)
    error_wf = wf.get("settings", {}).get("errorWorkflow")
    assert error_wf == GLOBAL_ERROR_WF_ID, (
        f"{wf_name}: settings.errorWorkflow must equal {GLOBAL_ERROR_WF_ID!r}, "
        f"got {error_wf!r}"
    )


def test_email_nodes_use_top_level_html_format():
    """
    Track A regression guard (verified live 2026-04-25):

    On n8n 2.13.4, emailSend@2 has TWO related blank-email bugs:
      1. options.emailFormat == "both" silently drops HTML.
      2. options.emailFormat (any value) is IGNORED — the v2 schema reads
         emailFormat ONLY from the parameters root, not from options.

    Verified fix: parameters.emailFormat = "html" at the top level
    (sibling of html, NOT under options). messageSize jumped from 355 to
    15493 bytes after the move.

    Rules:
      - When an emailSend node has an html field, parameters.emailFormat
        must be "html" at the TOP LEVEL.
      - emailFormat must NOT live under parameters.options on
        typeVersion < 2.1.
      - emailFormat == "both" is forbidden on typeVersion < 2.1.
    """
    violations: list[str] = []
    for path in sorted(WORKFLOW_DIR.glob("*.json")):
        wf = json.loads(path.read_text(encoding="utf-8"))
        for node in wf.get("nodes", []):
            if node.get("type") != "n8n-nodes-base.emailSend":
                continue
            params = node.get("parameters", {}) or {}
            opts = params.get("options", {}) or {}
            top_fmt = params.get("emailFormat")
            opt_fmt = opts.get("emailFormat")
            html = params.get("html")
            type_version = float(node.get("typeVersion", 0) or 0)
            name = node.get("name", "<unnamed>")
            label = f"{path.name}:{name}"

            # Forbidden: emailFormat under options on v2.
            if opt_fmt is not None and type_version < 2.1:
                violations.append(
                    f"{label} emailFormat is under options "
                    f"(on typeVersion={type_version}); n8n ignores it there. "
                    "Move to parameters.emailFormat (top level)."
                )

            if top_fmt == "both" and type_version < 2.1:
                violations.append(
                    f"{label} emailFormat='both' is forbidden on "
                    f"typeVersion={type_version} (use 'html' until 2.1)"
                )
                continue

            # If html present, top-level emailFormat must be 'html'.
            if isinstance(html, str) and html.strip():
                if top_fmt != "html":
                    violations.append(
                        f"{label} has html set but parameters.emailFormat="
                        f"{top_fmt!r} at top level (must be 'html')."
                    )
            elif top_fmt == "html":
                violations.append(
                    f"{label} emailFormat='html' but html parameter is empty"
                )
    assert not violations, (
        "Email-format violations (Track A regression guard):\n"
        + "\n".join(violations)
    )


def test_minio_download_nodes_have_continue_on_fail():
    violations: list[str] = []
    for path in sorted(WORKFLOW_DIR.glob("*.json")):
        wf = json.loads(path.read_text(encoding="utf-8"))
        for node in wf.get("nodes", []):
            if node.get("type") != "n8n-nodes-base.s3":
                continue
            op = node.get("parameters", {}).get("operation")
            if op != "download":
                continue
            if not node.get("continueOnFail"):
                violations.append(
                    f"{path.name}:{node.get('name', '<unnamed>')}"
                    f" S3 download missing continueOnFail"
                )
    assert not violations, (
        "Every S3 download node must set continueOnFail: true so offline "
        "errors can be branched on without firing the global error handler:\n"
        + "\n".join(violations)
    )


_SKIP_REASON_RE = re.compile(
    r"""skip_reason\s*:\s*['"]([a-z_]+)['"]""",
    re.VERBOSE,
)


def test_skip_reasons_use_canonical_enum():
    bad: list[str] = []
    for path in sorted(WORKFLOW_DIR.glob("*.json")):
        wf = json.loads(path.read_text(encoding="utf-8"))
        for node in wf.get("nodes", []):
            code = node.get("parameters", {}).get("jsCode", "") or ""
            for match in _SKIP_REASON_RE.finditer(code):
                value = match.group(1)
                if value not in ALLOWED_SKIP_REASONS:
                    bad.append(
                        f"{path.name}:{node.get('name', '<unnamed>')}"
                        f" uses skip_reason={value!r}"
                        f" (allowed: {sorted(ALLOWED_SKIP_REASONS)})"
                    )
    assert not bad, "\n".join(bad)


def test_morning_briefing_runs_after_brain_dump():
    bd = _load("brain-dump-processor-v2.json")
    mb = _load("morning-briefing.json")
    bd_min = _cron_minutes(bd)
    mb_min = _cron_minutes(mb)
    assert bd_min is not None, "brain-dump-processor-v2 missing cron expression"
    assert mb_min is not None, "morning-briefing missing cron expression"
    assert mb_min > bd_min, (
        f"morning-briefing ({mb_min} UTC minutes) must run strictly after "
        f"brain-dump-processor-v2 ({bd_min} UTC minutes) so the briefing "
        f"reflects today's captures, not yesterday's"
    )


# ── Task-runner contention guard ─────────────────────────────────────────────
# Workflows allowed to share a cron minute (e.g. fully manual job-search).
# Add explicit entries here only when contention has been verified safe.
ALLOWED_CRON_MINUTE_COLLISIONS: set[frozenset[str]] = set()


def _firing_slots(workflow: dict) -> set[tuple[str, int]]:
    """
    Return the set of distinct (hour_token, minute) firing slots for the workflow.

    hour_token is "*" for hourly crons, else the literal hour (e.g. "8" for
    "23 8 * * *"). Two daily workflows at minute 0 of different hours don't
    contend; two hourly workflows at minute 0 of any hour DO contend.

    triggerAtHour-style intervals fire at minute 0 of that hour.
    """
    slots: set[tuple[str, int]] = set()
    for node in workflow.get("nodes", []):
        if node.get("type") != "n8n-nodes-base.scheduleTrigger":
            continue
        for iv in node.get("parameters", {}).get("rule", {}).get("interval", []):
            expr = iv.get("expression")
            if expr:
                parts = expr.split()
                if len(parts) >= 2:
                    minute = int(parts[0]) if parts[0].isdigit() else 0
                    hour_tok = parts[1] if not parts[1].isdigit() else parts[1]
                    slots.add((hour_tok, minute))
                continue
            if "triggerAtHour" in iv:
                slots.add((str(iv["triggerAtHour"]), 0))
    return slots


def _has_code_node(workflow: dict) -> bool:
    return any(
        n.get("type") == "n8n-nodes-base.code"
        for n in workflow.get("nodes", [])
    )


def test_code_heavy_workflows_do_not_share_cron_minutes():
    """
    Two scheduled workflows that both contain Code nodes must not share an
    actual firing slot — that is the contention pattern that produced the
    'Task request timed out after 60 seconds' incident on 2026-04-29.

    A "slot" is the (hour_token, minute) tuple from the cron expression. Daily
    workflows at the same minute but different hours are NOT a collision; two
    hourly workflows at the same minute ARE.

    See RUNBOOK § Task-Runner Scheduling Slots.
    """
    by_slot: dict[tuple[str, int], set[str]] = {}
    for wf_name in SCHEDULED_WORKFLOWS:
        wf = _load(wf_name)
        if not _has_code_node(wf):
            continue
        for slot in _firing_slots(wf):
            by_slot.setdefault(slot, set()).add(wf_name)

    collisions: list[str] = []
    for (hour_tok, minute), names in by_slot.items():
        if len(names) <= 1:
            continue
        names_set = frozenset(names)
        if names_set in ALLOWED_CRON_MINUTE_COLLISIONS:
            continue
        slot_label = f"hour={hour_tok} minute=:{minute:02d}"
        collisions.append(
            f"  {slot_label} → {', '.join(sorted(names))}"
        )

    assert not collisions, (
        "Code-heavy workflows share cron firing slots — this triggers task-runner "
        "timeouts. Stagger the cron expressions (suggested slots: "
        ":03 :13 :23 :33 :43 :53) and rerun. Collisions:\n"
        + "\n".join(collisions)
    )


def test_execute_command_nodes_do_not_use_n8n_expression_with_shell_vars():
    """An executeCommand whose `command` starts with `=` is treated as an n8n
    expression. Bash parameter expansion `${VAR:-default}` is shell syntax,
    not n8n syntax — mixing them silently breaks at activation time.

    Regression: caught in 2026-05-03 AMBER pass on brain-dump-processor-v2.
    Drop the `=` so the command string is handed to bash verbatim and bash
    expands `${VAR:-default}` per POSIX.
    """
    violations: list[str] = []
    for wf_path in sorted(WORKFLOW_DIR.glob("*.json")):
        wf = json.loads(wf_path.read_text(encoding="utf-8"))
        for node in wf.get("nodes", []):
            if node.get("type") != "n8n-nodes-base.executeCommand":
                continue
            cmd = node.get("parameters", {}).get("command", "") or ""
            if cmd.startswith("=") and re.search(r"\$\{[A-Za-z_][A-Za-z0-9_]*:?[-?+=]", cmd):
                violations.append(
                    f"  {wf_path.name} :: {node.get('name','?')} — "
                    f"command starts with `=` AND contains bash parameter expansion"
                )

    assert not violations, (
        "executeCommand nodes mix n8n expression mode (leading `=`) with bash "
        "parameter expansion `${VAR:-default}`. Drop the `=` so the command "
        "is passed verbatim to bash:\n" + "\n".join(violations)
    )
