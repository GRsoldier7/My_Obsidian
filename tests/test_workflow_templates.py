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
    # "job-search-pipeline.json" — quarantined 2026-05-16 after the credentials
    # leak (docs/security/2026-05-16-INCIDENT-job-search-leak.md). When it's
    # rebuilt with placeholders + a fresh Google sheet, restore here.
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
    "daily_note_already_exists",
    "no_unenriched_urls",
    "no_enrichments_produced",
}

# Workflows whose log-write happens elsewhere OR via a path the regex
# detector can't see. Anything not in this set MUST be reachable from every
# IF branch — see `test_if_node_branches_always_reach_log_write`.
_LOG_WRITE_OPTIONAL = {
    # ai-brain is a sub-workflow; logs are written by its caller.
    "ai-brain.json",
    # telegram-capture is webhook-only and writes its log inline.
    "telegram-capture.json",
    # error-handler writes errors to its own dedicated bucket prefix.
    "error-handler.json",
    # weekend-planner has no log-write today; tracked as P2 followup.
    "weekend-planner.json",
    # HTTP-runner-proxied: the oho-runner sidecar writes the run log
    # server-side from tools/process_brain_dump.py + tools/build_command_
    # center.py. The workflow itself has no S3 log-write node, so the
    # `if-branch-reaches-log-write` detector can't see it. Logs verified
    # present in MinIO (37 brain-dump-processor logs, hourly live-dashboard
    # logs, twice-daily article-processor logs).
    "brain-dump-processor-v2.json",
    "live-dashboard-updater.json",
    "article-processor.json",
    # overdue-task-alert-v2 is being deactivated 2026-05-25 as a duplicate
    # of morning-briefing (CLAUDE.md "superseded by morning-briefing").
    # Allowlisted so the test passes; remove from SCHEDULED_WORKFLOWS once
    # the JSON is archived.
    "overdue-task-alert-v2.json",
}

# NOTE on system-health-monitor.json (REMOVED from allowlist 2026-05-29):
# This workflow was misclassified as having an IF-false-branch silent-log
# bug. The connections graph is:
#
#   Every 6 Hours (trigger)
#     → Init Checks
#     → S3: Check North Star
#     → S3: Check MTL
#     → Evaluate Results
#         ├──→ Any Failures? (IF; gates email only)
#         │       ├──→ Email: Health Alert   (TRUE branch)
#         │       └──→ []                    (FALSE branch — correct)
#         └──→ Convert Log to Binary → S3: Write Log   (parallel; always)
#
# `Any Failures?` only routes the email; log-writing happens on a parallel
# chain from `Evaluate Results`. The refined detection algorithm in
# `_every_if_branch_yields_log_write` now correctly tolerates this
# pattern. The historical "silent" symptom was the S3 headObject silent-
# bail (fixed 3560896 via `alwaysOutputData: true`), not the IF.

_LOG_WRITE_NODE_HINTS = (
    "write log",
    "write run log",
    "s3: write log",
    "s3: write run log",
)


def _is_log_write_node(node: dict) -> bool:
    name = str(node.get("name", "")).lower()
    return any(hint in name for hint in _LOG_WRITE_NODE_HINTS)


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


def test_brain_dump_processor_uses_oho_runner_http_boundary():
    """P1 brain-dump processing must stay on the n8n 2.x-safe runner path.

    Regression: n8n 2.18.5 refused to activate the `executeCommand` node, and
    the n8n Docker container could not see host `/opt/oho`. The workflow must
    call the dedicated `oho-runner` sidecar instead.
    """
    workflow = json.loads((WORKFLOW_DIR / "brain-dump-processor-v2.json").read_text(encoding="utf-8"))
    nodes = workflow.get("nodes", [])

    execute_nodes = [
        node.get("name")
        for node in nodes
        if node.get("type") == "n8n-nodes-base.executeCommand"
    ]
    assert execute_nodes == []

    runner_nodes = [
        node
        for node in nodes
        if node.get("type") == "n8n-nodes-base.httpRequest"
        and "/process-brain-dump" in node.get("parameters", {}).get("url", "")
    ]
    assert len(runner_nodes) == 1

    runner_node = runner_nodes[0]
    assert runner_node["parameters"]["url"] == "http://oho-runner:8080/process-brain-dump"
    assert runner_node["parameters"]["method"] == "POST"
    assert runner_node["credentials"]["httpHeaderAuth"]["id"] == "__OHO_RUNNER_CRED_ID__"
    assert runner_node["credentials"]["httpHeaderAuth"]["name"] == "OHO Runner Auth"


# ── Brain-dump processor: silent-on-no_work email policy ─────────────────────


def _load_brain_dump_processor() -> dict:
    return json.loads(
        (WORKFLOW_DIR / "brain-dump-processor-v2.json").read_text(encoding="utf-8")
    )


def _node(wf: dict, name: str) -> dict | None:
    for n in wf.get("nodes", []):
        if n.get("name") == name:
            return n
    return None


def _conditions(if_node: dict) -> list[dict]:
    return (
        if_node.get("parameters", {})
        .get("conditions", {})
        .get("conditions", [])
    )


def test_brain_dump_processor_no_work_path_is_silent():
    """When the runner reports `top_status == 'no_work'`, no email should fire.

    Empty-day heartbeat is suppressed by design — the run log + audit already
    record the no-op. We enforce this with a chained IF: ``Has Work?`` false
    branch flows into ``Is Error?``, whose false branch (``top_status ==
    'no_work'``) is intentionally unwired.

    Regression: prior to 2026-05-04 the false branch of ``Has Work?`` went
    directly to ``Email: No-Work / Error Notice``, which fired every empty
    day.
    """
    wf = _load_brain_dump_processor()

    # Old node must be gone; new node must exist.
    assert _node(wf, "Email: No-Work / Error Notice") is None, (
        "Email: No-Work / Error Notice still present — workflow hasn't been "
        "migrated to the silent-no_work policy"
    )
    err_email = _node(wf, "Email: Error Notice")
    assert err_email is not None, "Email: Error Notice node missing"
    assert err_email.get("type") == "n8n-nodes-base.emailSend"

    # Has Work? is the success/non-success split.
    has_work = _node(wf, "Has Work?")
    assert has_work is not None and has_work.get("type") == "n8n-nodes-base.if"
    hw_conds = _conditions(has_work)
    assert any(
        c.get("rightValue") == "success"
        and c.get("operator", {}).get("operation") == "equals"
        for c in hw_conds
    ), f"Has Work? must equals 'success'; got {hw_conds!r}"

    # Is Error? must filter out 'no_work' before the error email.
    is_err = _node(wf, "Is Error?")
    assert is_err is not None, "Is Error? IF missing — no_work would still email"
    assert is_err.get("type") == "n8n-nodes-base.if"
    ie_conds = _conditions(is_err)
    assert any(
        c.get("rightValue") == "no_work"
        and c.get("operator", {}).get("operation") == "notEquals"
        for c in ie_conds
    ), f"Is Error? must notEquals 'no_work'; got {ie_conds!r}"

    # Connection wiring: Has Work? false → Is Error?; Is Error? true →
    # Email: Error Notice; Is Error? false branch must be empty (silent end).
    conns = wf.get("connections") or {}
    hw_branches = (conns.get("Has Work?") or {}).get("main") or []
    assert len(hw_branches) >= 2, "Has Work? must have true + false branches"
    hw_false_targets = [c.get("node") for c in (hw_branches[1] or [])]
    assert hw_false_targets == ["Is Error?"], (
        f"Has Work? false branch must go to Is Error?; got {hw_false_targets!r}"
    )

    ie_branches = (conns.get("Is Error?") or {}).get("main") or []
    assert len(ie_branches) >= 2, "Is Error? must have true + false branches"
    ie_true_targets = [c.get("node") for c in (ie_branches[0] or [])]
    ie_false_targets = [c.get("node") for c in (ie_branches[1] or [])]
    assert ie_true_targets == ["Email: Error Notice"], (
        f"Is Error? true branch must go to Email: Error Notice; "
        f"got {ie_true_targets!r}"
    )
    assert ie_false_targets == [], (
        f"Is Error? false branch (the no_work case) must be UNWIRED so the "
        f"workflow ends silently; got {ie_false_targets!r}"
    )


def test_brain_dump_processor_has_no_email_directly_after_has_work_false():
    """Belt-and-suspenders: rule out a future regression where someone wires
    an email back into ``Has Work?``'s false branch directly.
    """
    wf = _load_brain_dump_processor()
    has_work = _node(wf, "Has Work?")
    assert has_work is not None
    branches = (wf.get("connections") or {}).get("Has Work?", {}).get("main") or []
    if len(branches) < 2:
        pytest.fail("Has Work? missing branches")
    false_targets = [c.get("node") for c in (branches[1] or [])]
    by_name = {n.get("name"): n for n in wf.get("nodes", [])}
    bad = [
        t for t in false_targets
        if (by_name.get(t) or {}).get("type") == "n8n-nodes-base.emailSend"
    ]
    assert not bad, (
        f"Has Work? false branch points directly at an email node ({bad!r}). "
        f"Insert an Is Error? IF that filters out 'no_work' first."
    )


# ── Log-write reachability (regression: 6-week silent gap on
# daily-note-creator-v2 caught 2026-05-25; the IF node's false branch was
# terminal `[]` so the run-log node never fired on steady-state runs) ──

def _load_workflow(name: str) -> dict:
    return json.loads((WORKFLOW_DIR / name).read_text(encoding="utf-8"))


def _reachable_from(wf: dict, start: str) -> set[str]:
    """BFS over the n8n connections graph starting from a node name."""
    conns = wf.get("connections") or {}
    seen: set[str] = set()
    stack = [start]
    while stack:
        cur = stack.pop()
        if cur in seen:
            continue
        seen.add(cur)
        for tgt in iter_targets(conns.get(cur) or {}):
            stack.append(tgt)
    return seen


def _reachable_from_skipping(wf: dict, start: str, *, skip: str) -> set[str]:
    """BFS that refuses to traverse THROUGH a named node. Used to decide
    whether a log-write is reachable via a path that bypasses a given IF.
    A workflow can correctly leave an IF's false branch as ``[]`` when the
    IF only gates a side-effect (e.g. email) while log-writing lives on a
    parallel chain — see system-health-monitor: `Evaluate Results` fans
    out to BOTH `Any Failures?` (IF; gates email) AND `Convert Log to
    Binary` → `S3: Write Log` (always-runs)."""
    conns = wf.get("connections") or {}
    seen: set[str] = set()
    stack = [start]
    while stack:
        cur = stack.pop()
        if cur in seen or cur == skip:
            continue
        seen.add(cur)
        for tgt in iter_targets(conns.get(cur) or {}):
            stack.append(tgt)
    return seen


def _trigger_node_names(wf: dict) -> list[str]:
    """Trigger nodes are roots of the graph; any node whose type ends in
    Trigger OR is a webhook entry."""
    out = []
    for n in wf.get("nodes", []):
        t = str(n.get("type", "")).lower()
        if t.endswith("trigger") or t.endswith("webhook"):
            out.append(n["name"])
    return out


def _every_if_branch_yields_log_write(wf: dict, log_nodes: set[str]) -> list[str]:
    """Return list of `(if_node, branch_index)` strings whose downstream
    reachable set does not include any log-write node AND for which no
    parallel-chain path from a trigger reaches a log-write while
    bypassing this IF.

    Refined 2026-05-29 after the system-health-monitor misclassification:
    the original algorithm flagged any IF whose false branch was
    terminal `[]`. That is over-strict — an IF whose only role is to
    gate a side-effect (email, notification) is correctly terminal on
    its non-firing branch as long as log-writing is on a parallel
    branch that does not depend on the IF firing. The refined check
    keeps the original tight invariant for IFs that are the ONLY path
    to log-write (the daily-note-creator-v2 + link-enricher case), but
    tolerates IFs whose absence still leaves a log-write reachable from
    a trigger.
    """
    conns = wf.get("connections") or {}
    by_name = {n["name"]: n for n in wf.get("nodes", [])}
    trigger_names = _trigger_node_names(wf)
    bad = []
    for node_name, node in by_name.items():
        if str(node.get("type", "")) != "n8n-nodes-base.if":
            continue
        branches = (conns.get(node_name) or {}).get("main") or []
        for idx, branch in enumerate(branches):
            # 1. Branch itself reaches log-write — OK
            reached_via_branch: set[str] = set()
            for item in branch:
                if isinstance(item, dict) and item.get("node"):
                    reached_via_branch |= _reachable_from(wf, item["node"])
            if reached_via_branch & log_nodes:
                continue

            # 2. A parallel chain from a trigger reaches log-write even
            #    if this IF is removed — also OK (the IF only gates a
            #    side-effect like email; log-write is unconditional).
            bypassed: set[str] = set()
            for trig in trigger_names:
                bypassed |= _reachable_from_skipping(wf, trig, skip=node_name)
            if bypassed & log_nodes:
                continue

            # Otherwise: the workflow relies on this IF firing to write a
            # log, and this branch fails to do so. Real silent-log bug.
            bad.append(f"{node_name}[{idx}]")
    return bad


@pytest.mark.parametrize("wf_name", SCHEDULED_WORKFLOWS)
def test_if_node_branches_always_reach_log_write(wf_name):
    """Every IF node in a scheduled workflow must have BOTH branches
    eventually reach a run-log write node. Empty terminal `[]` branches are
    forbidden because they cause silent log gaps (see daily-note-creator-v2
    incident, 6 weeks of silent runs, caught 2026-05-25).

    Workflows that legitimately have no log-write step are listed in
    ``_LOG_WRITE_OPTIONAL`` above.
    """
    if wf_name in _LOG_WRITE_OPTIONAL:
        pytest.skip(f"{wf_name} is in _LOG_WRITE_OPTIONAL allowlist")
    wf = _load_workflow(wf_name)
    log_nodes = {n["name"] for n in wf.get("nodes", []) if _is_log_write_node(n)}
    if not log_nodes:
        pytest.fail(
            f"{wf_name}: no log-write node found. "
            "Add an `S3: Write Log` / `S3: Write Run Log` node, or add the "
            "workflow to _LOG_WRITE_OPTIONAL with a documented reason."
        )
    bad = _every_if_branch_yields_log_write(wf, log_nodes)
    assert not bad, (
        f"{wf_name}: IF branches with no path to a log-write node: {bad!r}. "
        "Wire the empty branch to a `Build Noop Log` Code node that emits a "
        "`status: \"skipped\"` log with a canonical `skip_reason`, then into "
        "the existing S3 log-writer."
    )


# ── S3 headObject silent-bail regression guard (NEXT-STEPS item 10b) ──
# n8n 2.x `n8n-nodes-base.s3` headObject succeeds silently without emitting
# a downstream item when the file exists + continueOnFail=true. That broke
# system-health-monitor for weeks (zero logs in MinIO; n8n said success).
# `alwaysOutputData: true` forces an item even on empty success → chain
# continues. This test prevents the flag from being silently dropped.

_HEAD_OBJECT_WORKFLOWS_REQUIRING_ALWAYS_OUTPUT = {
    # workflow name : set of node names that MUST carry alwaysOutputData
    "system-health-monitor.json": {
        "S3: Check North Star",
        "S3: Check MTL",
    },
}


@pytest.mark.parametrize("wf_name", sorted(_HEAD_OBJECT_WORKFLOWS_REQUIRING_ALWAYS_OUTPUT))
def test_head_object_nodes_use_always_output_data(wf_name):
    """Per NEXT-STEPS item 10b: any S3 `headObject` node whose downstream is
    another S3 node (or any node that needs an input item) MUST set
    ``alwaysOutputData: true``; otherwise a success-with-no-error returns
    no item and the flow dies silently. Verified empirically against the
    system-health-monitor execution trace (lastNodeExecuted = first
    headObject, downstream nodes never fired)."""
    wf = _load_workflow(wf_name)
    required = _HEAD_OBJECT_WORKFLOWS_REQUIRING_ALWAYS_OUTPUT[wf_name]
    by_name = {n["name"]: n for n in wf.get("nodes", [])}
    missing = []
    for node_name in sorted(required):
        node = by_name.get(node_name)
        if node is None:
            missing.append(f"{node_name!r} (node missing)")
            continue
        if not node.get("alwaysOutputData"):
            missing.append(f"{node_name!r} (alwaysOutputData not set)")
    assert not missing, (
        f"{wf_name}: nodes must declare `alwaysOutputData: true` to avoid "
        f"silent S3-chain bail: {missing!r}"
    )
