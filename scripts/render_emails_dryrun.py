#!/usr/bin/env python3
"""
scripts/render_emails_dryrun.py

Dry-run the Build/Format Code node from each email-emitting workflow with
synthetic data and render the produced HTML to tests/fixtures/email-previews/
so the operator can visually review the layout in a browser without having to
trigger n8n executions.

Idempotent: overwrites the preview HTML for each workflow on every run.

The script extracts the JS source out of the workflow JSON's Build/Format
Code node, wraps it in a tiny Node.js shim that injects synthetic
`$input`/`$()`/`this.helpers` accessors, runs `node` to evaluate it, and
captures the produced `json.html` field.

Why Node and not Python: the Build nodes are real JS and we want the actual
template that ships, not a Python re-implementation that can drift.

Usage:
    set -a && source .env && set +a && python3 scripts/render_emails_dryrun.py

Requires `node` on PATH (n8n already requires it).
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
WORKFLOW_DIR = REPO_ROOT / "workflows" / "n8n"
PREVIEW_DIR = REPO_ROOT / "tests" / "fixtures" / "email-previews"

# Each entry: workflow filename → which Code-node id contains the HTML build,
# plus a synthetic context the shim should inject.
TARGETS = [
    {
        "workflow": "morning-briefing.json",
        "build_node_id": "build-briefing",
        "context": {
            "Set Dates": {
                "today": "2026-04-25",
                "yesterday": "2026-04-24",
                "dayOfWeek": "Saturday",
            },
            "Decode MTL": {
                "_text": (
                    "# Master Task List\n\n"
                    "- [ ] Call Dr. Smith about hip MRI [area:: health] [priority:: A] [due:: 2026-04-23]\n"
                    "- [ ] Ship Echelon Seven MVP outreach [area:: business] [priority:: A]\n"
                    "- [ ] Marriage check-in with Christy [area:: family] [priority:: A] [due:: 2026-04-25]\n"
                    "- [ ] Buy groceries [area:: personal] [priority:: C]\n"
                    "- [ ] Reply to Union project email [area:: work] [priority:: B] [due:: 2026-04-25]\n"
                ),
            },
            # Yesterday log fed in via binary[0]
            "_binary_0": json.dumps(
                {
                    "workflow": "brain-dump-processor",
                    "tasks_extracted": 5,
                    "articles_queued": 3,
                }
            ),
        },
    },
    {
        "workflow": "weekly-digest-v2.json",
        "build_node_id": "build-digest",
        "context": {
            "_binary_0": (
                "# Master Task List\n\n"
                "- [ ] Faith rock task [area:: faith] [priority:: A] [due:: 2026-04-26]\n"
                "- [ ] Business outreach [area:: business] [priority:: A]\n"
                "- [ ] Old overdue task [area:: work] [priority:: B] [due:: 2026-04-10]\n"
                "- [x] Completed gym session [area:: health]\n"
                "- [x] Completed sermon prep [area:: faith]\n"
            ),
        },
    },
    {
        "workflow": "vault-health-report.json",
        "build_node_id": "build-report",
        "context": {
            "Collect Brain Dumps": {
                "today": "2026-04-25",
                "dayOfWeek": "Saturday",
                "weekStart": "2026-04-21",
                "braindumpFiles": [
                    {"key": "00_Inbox/brain-dumps/Personal.md", "name": "Personal.md", "sizeKB": 2},
                    {"key": "00_Inbox/brain-dumps/Work.md", "name": "Work.md", "sizeKB": 1},
                ],
                "braindumpCount": 2,
                "processedThisWeek": [
                    {"key": "00_Inbox/processed/2026-04-22-test-tasks.md", "name": "2026-04-22-test-tasks.md"},
                ],
                "processedCount": 1,
            },
            "Decode Articles": {
                "_text": (
                    "## Added 2026-04-25\n"
                    "- [How to Build Habits](https://example.com/habits) — context [title:: Atomic Habits primer] [description:: deep dive]\n"
                    "- https://example.com/raw-link-1\n"
                    "- https://example.com/raw-link-2\n"
                ),
            },
            "_input_first": {
                "today": "2026-04-25",
                "weekStart": "2026-04-21",
                "braindumpFiles": [
                    {"key": "00_Inbox/brain-dumps/Personal.md", "name": "Personal.md", "sizeKB": 2},
                    {"key": "00_Inbox/brain-dumps/Work.md", "name": "Work.md", "sizeKB": 1},
                ],
                "braindumpCount": 2,
                "processedThisWeek": [
                    {"key": "00_Inbox/processed/2026-04-22-test-tasks.md", "name": "2026-04-22-test-tasks.md"},
                ],
                "processedCount": 1,
            },
        },
    },
    {
        "workflow": "overdue-task-alert-v2.json",
        "build_node_id": "format-email",
        # Synthetic input for both branches: present + empty.
        "context": {
            "_input_first": {
                "overdue": [
                    {
                        "task": "Call Dr. Smith about hip MRI",
                        "area": "health",
                        "priority": "A",
                        "due": "2026-04-15",
                        "daysOverdue": 10,
                        "urgency": "critical",
                    },
                    {
                        "task": "Reply to Union project email",
                        "area": "work",
                        "priority": "B",
                        "due": "2026-04-22",
                        "daysOverdue": 3,
                        "urgency": "medium",
                    },
                ],
                "count": 2,
                "today": "2026-04-25",
            },
        },
    },
    {
        "workflow": "error-handler.json",
        "build_node_id": "format-error",
        "context": {
            "_input_first": {
                "workflow": {"id": "d8qgXRCfRpHHHopL", "name": "🌅 Morning Briefing"},
                "execution": {
                    "id": "9876543",
                    "lastNodeExecuted": "S3: Read MTL",
                    "error": {
                        "message": "AccessDenied: The Access Key Id you provided does not exist",
                        "stack": "AccessDenied at S3.send (/n8n/node_modules/aws-sdk/...)",
                    },
                },
            },
        },
    },
    {
        "workflow": "system-health-monitor.json",
        "build_node_id": "evaluate",
        "context": {
            "Init Checks": {
                "today": "2026-04-25",
                "logKey": "99_System/logs/health-monitor-2026-04-25-12.json",
            },
            "S3: Check North Star": {"error": None},
            "S3: Check MTL": {"error": "Connection refused: 192.168.1.240:9000"},
        },
    },
]


def _extract_build_node(workflow_path: Path, node_id: str) -> dict:
    """Return the n8n Code node whose id matches `node_id`."""
    with workflow_path.open("r", encoding="utf-8") as f:
        wf = json.load(f)
    for node in wf.get("nodes", []):
        if node.get("id") == node_id:
            return node
    raise SystemExit(f"node id={node_id!r} not found in {workflow_path.name}")


def _build_shim(node_js: str, context: dict) -> str:
    """
    Wrap the Code node JS into a Node.js executable shim that injects:
      - $('NodeName') accessor returning .first().json
      - $input.first() / $input.all()
      - this.helpers.getBinaryDataBuffer(idx, 'data')
      - $now.toISO() / $json (just-in-case)
    Then run the node body in an async IIFE and print the resulting json.html.
    """
    ctx_json = json.dumps(context)
    return f"""
const ctx = {ctx_json};

const helpers = {{
  async getBinaryDataBuffer(idx, _name) {{
    const key = '_binary_' + idx;
    const v = ctx[key];
    if (v === undefined) return Buffer.alloc(0);
    return Buffer.from(typeof v === 'string' ? v : JSON.stringify(v), 'utf-8');
  }}
}};

function $(name) {{
  const data = ctx[name] || {{}};
  return {{ first: () => ({{ json: data }}) }};
}}

const $input = {{
  first: () => ({{ json: ctx._input_first || {{}} }}),
  all: () => Array.isArray(ctx._input_all)
    ? ctx._input_all.map(j => ({{ json: j }}))
    : [{{ json: ctx._input_first || {{}} }}],
}};

const $json = ctx._input_first || {{}};
const $now = {{
  toISO: () => new Date().toISOString(),
  format: (fmt) => new Date().toISOString().split('T')[0],
}};

(async () => {{
  try {{
    const result = await (async function() {{
      {node_js}
    }}).call({{ helpers }});
    const first = Array.isArray(result) ? result[0] : result;
    const out = first && first.json ? first.json : first;
    process.stdout.write(JSON.stringify({{
      html: out.html || '',
      subject: out.subject || '',
      bodyLength: (out.html || '').length,
    }}));
  }} catch (e) {{
    process.stderr.write('SHIM ERROR: ' + (e.stack || e.message || String(e)));
    process.exit(2);
  }}
}})();
"""


def render_one(target: dict) -> dict:
    workflow_path = WORKFLOW_DIR / target["workflow"]
    node = _extract_build_node(workflow_path, target["build_node_id"])
    js_src = node["parameters"]["jsCode"]
    shim = _build_shim(js_src, target["context"])

    with tempfile.NamedTemporaryFile(
        "w", suffix=".js", delete=False, encoding="utf-8"
    ) as tmp:
        tmp.write(shim)
        tmp_path = Path(tmp.name)

    try:
        result = subprocess.run(
            ["node", str(tmp_path)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
        )
    finally:
        try:
            tmp_path.unlink()
        except OSError:
            pass

    if result.returncode != 0:
        return {
            "workflow": target["workflow"],
            "ok": False,
            "error": (result.stderr or "")[:500],
        }

    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as e:
        return {
            "workflow": target["workflow"],
            "ok": False,
            "error": f"shim stdout not JSON: {e}; got {result.stdout[:200]}",
        }

    out_path = PREVIEW_DIR / (target["workflow"].replace(".json", ".html"))
    out_path.write_text(payload["html"], encoding="utf-8")
    return {
        "workflow": target["workflow"],
        "ok": True,
        "preview": str(out_path),
        "bodyLength": payload["bodyLength"],
        "subject": payload["subject"],
    }


def main() -> int:
    if shutil.which("node") is None:
        print("ERROR: 'node' not on PATH. Install Node.js or add it to PATH.")
        return 2
    PREVIEW_DIR.mkdir(parents=True, exist_ok=True)

    print("Rendering email previews...")
    print(f"  Output dir: {PREVIEW_DIR}")
    print()

    failures = 0
    for target in TARGETS:
        result = render_one(target)
        if result["ok"]:
            print(f"  OK  {result['workflow']:35s}  {result['bodyLength']:>6} B  -> {result['preview']}")
        else:
            failures += 1
            print(f"  FAIL {result['workflow']:35s}  {result['error']}")

    print()
    print(f"Done: {len(TARGETS) - failures}/{len(TARGETS)} previews rendered.")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
