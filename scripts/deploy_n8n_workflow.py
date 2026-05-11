#!/usr/bin/env python3
"""Targeted single-workflow n8n deploy: backup → hydrate → PUT → verify → optional activate.

Mirrors the hydration semantics of scripts/setup-n8n.sh (placeholder set, cred-ID
discovery, read-only field stripping, allowed settings keys), but operates on
exactly one workflow file. Use this for surgical deploys when setup-n8n.sh's
full reconciliation is too broad.

Required env: N8N_HOST, N8N_API_KEY. Optional: NOTIFICATION_EMAIL.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import pathlib
import re
import sys
import urllib.error
import urllib.request
from typing import Any

CRED_NAMES = {
    "__MINIO_CRED_ID__":       ("MinIO S3",           "s3"),
    "__SMTP_CRED_ID__":        ("Gmail SMTP (Aaron)", "smtp"),
    "__OPENROUTER_CRED_ID__":  ("OpenRouter API",     "httpHeaderAuth"),
    "__GCAL_CRED_ID__":        ("Google Calendar",    "googleCalendarOAuth2Api"),
    "__OHO_RUNNER_CRED_ID__":  ("OHO Runner Auth",    "httpHeaderAuth"),
}

READONLY_FIELDS = ("tags", "staticData", "id", "triggerCount",
                   "updatedAt", "versionId", "createdAt")
ALLOWED_SETTINGS = {"executionOrder", "saveManualExecutions",
                    "callerPolicy", "errorWorkflow", "timezone"}

PLACEHOLDER_RE = re.compile(r"__[A-Z_]+__")


def _api(method: str, path: str, *, host: str, key: str, body: Any = None) -> Any:
    url = f"{host}/api/v1{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("X-N8N-API-KEY", key)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        sys.exit(f"HTTP {e.code} on {method} {path}: "
                 f"{e.read().decode(errors='replace')[:600]}")


def _list_workflows(host: str, key: str) -> list[dict]:
    return _api("GET", "/workflows", host=host, key=key).get("data", [])


def _find_credential_ids(host: str, key: str, needed: set[str]) -> dict[str, str | None]:
    """Walk live workflows; for each cred placeholder, return first matching id."""
    found: dict[str, str | None] = {ph: None for ph in needed}
    if not needed:
        return found
    for w in _list_workflows(host, key):
        if all(found[ph] for ph in needed):
            break
        full = _api("GET", f"/workflows/{w['id']}", host=host, key=key)
        for node in full.get("nodes", []):
            creds = node.get("credentials") or {}
            for ph in needed:
                if found[ph]:
                    continue
                cname, ckey = CRED_NAMES[ph]
                cred = creds.get(ckey)
                if cred and cred.get("name") == cname:
                    found[ph] = cred.get("id")
    return found


def _hydrate(template_text: str, replacements: dict[str, str | None],
             error_workflow_id: str | None, template_filename: str) -> dict:
    placeholders = set(PLACEHOLDER_RE.findall(template_text))
    text = template_text
    for ph in placeholders:
        val = replacements.get(ph)
        if val is None:
            sys.exit(f"FATAL: template uses {ph} but no value resolved")
        text = text.replace(ph, val)
    leftover = PLACEHOLDER_RE.findall(text)
    if leftover:
        sys.exit(f"FATAL: unhydrated placeholders remain: {sorted(set(leftover))}")
    wf = json.loads(text)
    for f in READONLY_FIELDS:
        wf.pop(f, None)
    settings = wf.get("settings") or {}
    settings = {k: v for k, v in settings.items() if k in ALLOWED_SETTINGS}
    if error_workflow_id and template_filename != "error-handler.json":
        settings.setdefault("errorWorkflow", error_workflow_id)
    wf["settings"] = settings
    return wf


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("template", help="Path to workflows/n8n/<name>.json")
    p.add_argument("--workflow-id",
                   help="Live workflow id to update (default: look up by name)")
    p.add_argument("--activate", action="store_true",
                   help="Activate after successful PUT + assertions pass")
    p.add_argument("--no-backup", action="store_true",
                   help="Skip backup of current live workflow JSON")
    p.add_argument("--backup-dir", default="/opt/oho/backups/n8n")
    p.add_argument("--assert-nodes", type=int,
                   help="Fail unless re-fetched workflow has exactly N nodes")
    p.add_argument("--assert-execute-command-contains", action="append", default=[],
                   metavar="SUBSTRING",
                   help="Fail unless at least one executeCommand node's command "
                        "contains this substring (repeatable)")
    p.add_argument("--assert-no-execute-command", action="store_true",
                   help="Fail if any executeCommand node is present")
    p.add_argument("--assert-http-url-contains", action="append", default=[],
                   metavar="SUBSTRING",
                   help="Fail unless at least one httpRequest node's URL contains "
                        "this substring (repeatable)")
    args = p.parse_args()

    host = os.environ.get("N8N_HOST")
    key = os.environ.get("N8N_API_KEY")
    if not host or not key:
        sys.exit("ERROR: N8N_HOST and N8N_API_KEY must be set in env")

    template_path = pathlib.Path(args.template).resolve()
    if not template_path.exists():
        sys.exit(f"ERROR: template not found: {template_path}")
    template_text = template_path.read_text()
    template_obj = json.loads(template_text)
    name = template_obj["name"]
    placeholders = set(PLACEHOLDER_RE.findall(template_text))
    cred_phs = placeholders & CRED_NAMES.keys()

    print(f"template:      {template_path}")
    print(f"workflow name: {name!r}")
    print(f"placeholders:  {sorted(placeholders) or '(none)'}")

    # Resolve replacements: cred-walking first; env-var fallback for any
    # placeholder the walker can't find (covers first-deploy case where the
    # credential isn't bound to any existing workflow yet).
    replacements: dict[str, str | None] = {}
    if cred_phs:
        cred_ids = _find_credential_ids(host, key, cred_phs)
        for ph, val in cred_ids.items():
            cname, _ = CRED_NAMES[ph]
            if val is None:
                env_var = ph.strip("_")
                env_val = os.environ.get(env_var)
                if env_val:
                    print(f"  {ph} -> {env_val}  "
                          f"(cred {cname!r} not in any live workflow; "
                          f"using env {env_var})")
                    replacements[ph] = env_val
                else:
                    print(f"  {ph} -> NONE  (cred name: {cname!r})")
                    replacements[ph] = None
            else:
                print(f"  {ph} -> {val}  (cred name: {cname!r})")
                replacements[ph] = val
    if "__NOTIFICATION_EMAIL__" in placeholders:
        notify = os.environ.get("NOTIFICATION_EMAIL", "")
        if not notify:
            sys.exit("FATAL: __NOTIFICATION_EMAIL__ in template but "
                     "NOTIFICATION_EMAIL env var not set")
        replacements["__NOTIFICATION_EMAIL__"] = notify
        print(f"  __NOTIFICATION_EMAIL__ -> {notify}")
    for ph in placeholders - cred_phs - {"__NOTIFICATION_EMAIL__"}:
        env_var = ph.strip("_")
        v = os.environ.get(env_var)
        if v is None:
            sys.exit(f"FATAL: unsupported placeholder {ph} "
                     f"(env {env_var} not set)")
        replacements[ph] = v
        print(f"  {ph} -> (from env {env_var})")

    # Resolve target workflow id
    workflow_id = args.workflow_id
    if not workflow_id:
        for w in _list_workflows(host, key):
            if w.get("name") == name:
                workflow_id = w["id"]
                break

    backup_path: pathlib.Path | None = None
    if workflow_id:
        live = _api("GET", f"/workflows/{workflow_id}", host=host, key=key)
        live_name = live.get("name")
        if live_name != name:
            sys.exit(f"FATAL: live workflow id {workflow_id} is named "
                     f"{live_name!r}, template is {name!r} — refusing to clobber")
        print(f"target:        id={workflow_id} active={live.get('active')} "
              f"nodes={len(live.get('nodes') or [])}")
        if not args.no_backup:
            backup_dir = pathlib.Path(args.backup_dir)
            backup_dir.mkdir(parents=True, exist_ok=True)
            ts = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            backup_path = backup_dir / f"{template_path.stem}-{ts}.json"
            backup_path.write_text(json.dumps(live, indent=2, sort_keys=True))
            print(f"backup:        {backup_path}")
    else:
        print(f"target:        no live workflow named {name!r} — will CREATE")

    # Hydrate
    settings_in_tpl = template_obj.get("settings") or {}
    error_wf_id = settings_in_tpl.get("errorWorkflow")
    wf_body = _hydrate(template_text, replacements,
                       error_workflow_id=error_wf_id,
                       template_filename=template_path.name)
    wf_body["name"] = name

    # PUT or POST
    if workflow_id:
        print(f"PUT /workflows/{workflow_id} "
              f"(nodes={len(wf_body.get('nodes', []))})")
        _api("PUT", f"/workflows/{workflow_id}",
             host=host, key=key, body=wf_body)
    else:
        print(f"POST /workflows (nodes={len(wf_body.get('nodes', []))})")
        result = _api("POST", "/workflows", host=host, key=key, body=wf_body)
        workflow_id = result.get("id")
        if not workflow_id:
            sys.exit(f"ERROR: create returned no id: {result!r}")
        print(f"created id={workflow_id}")

    # Verify
    final = _api("GET", f"/workflows/{workflow_id}",
                 host=host, key=key)
    nodes = final.get("nodes") or []
    print(f"verify:        name={final.get('name')!r}  "
          f"nodes={len(nodes)}  active={final.get('active')}")
    if final.get("name") != name:
        sys.exit(f"ASSERT FAIL: name changed to {final.get('name')!r}")
    if args.assert_nodes is not None and len(nodes) != args.assert_nodes:
        sys.exit(f"ASSERT FAIL: node count {len(nodes)} != "
                 f"expected {args.assert_nodes}")
    if args.assert_execute_command_contains:
        commands = [
            (n.get("name"), n.get("parameters", {}).get("command", ""))
            for n in nodes
            if n.get("type") == "n8n-nodes-base.executeCommand"
        ]
        if not commands:
            sys.exit("ASSERT FAIL: no executeCommand nodes present")
        for needle in args.assert_execute_command_contains:
            if not any(needle in c for _, c in commands):
                cmds_repr = "\n".join(f"  - {n}: {c!r}" for n, c in commands)
                sys.exit(f"ASSERT FAIL: no executeCommand contains "
                         f"{needle!r}; commands were:\n{cmds_repr}")
            print(f"  OK executeCommand contains: {needle!r}")
    if args.assert_no_execute_command:
        ec_nodes = [n.get("name") for n in nodes
                    if n.get("type") == "n8n-nodes-base.executeCommand"]
        if ec_nodes:
            sys.exit(f"ASSERT FAIL: executeCommand nodes present: {ec_nodes}")
        print("  OK no executeCommand nodes")
    if args.assert_http_url_contains:
        urls = [
            (n.get("name"), n.get("parameters", {}).get("url", ""))
            for n in nodes
            if n.get("type") == "n8n-nodes-base.httpRequest"
        ]
        if not urls:
            sys.exit("ASSERT FAIL: no httpRequest nodes present")
        for needle in args.assert_http_url_contains:
            if not any(needle in u for _, u in urls):
                urls_repr = "\n".join(f"  - {n}: {u!r}" for n, u in urls)
                sys.exit(f"ASSERT FAIL: no httpRequest URL contains "
                         f"{needle!r}; urls were:\n{urls_repr}")
            print(f"  OK httpRequest URL contains: {needle!r}")

    # Activate
    if args.activate:
        _api("POST", f"/workflows/{workflow_id}/activate",
             host=host, key=key)
        verify2 = _api("GET", f"/workflows/{workflow_id}",
                       host=host, key=key)
        print(f"activate:      active={verify2.get('active')}")
        if not verify2.get("active"):
            sys.exit("ASSERT FAIL: workflow did not activate")

    print(f"DONE  id={workflow_id}  name={name!r}  backup={backup_path}")


if __name__ == "__main__":
    main()
