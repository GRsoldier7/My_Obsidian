#!/usr/bin/env python3
"""
Deploy fixed n8n workflows to live instance.
Filters out fields the API rejects (tags, versionId, triggerCount, updatedAt).
"""
import sys
import json
import urllib.request
import urllib.error
import os

sys.stdout.reconfigure(encoding='utf-8')

N8N_HOST = os.environ.get('N8N_HOST', 'http://192.168.1.121:5678')
N8N_API_KEY = os.environ.get('N8N_API_KEY', '')
API = f'{N8N_HOST}/api/v1'

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
WORKFLOW_DIR = os.path.join(SCRIPT_DIR, '..', 'workflows', 'n8n')

WORKFLOWS = [
    'brain-dump-processor.json',
    'daily-note-creator.json',
    'overdue-task-alert.json',
    'article-processor.json',
    'weekly-digest.json',
    'ai-brain.json',
]

ALLOWED_FIELDS = {'name', 'nodes', 'connections', 'settings', 'staticData'}

def api_request(method, path, body=None):
    url = f'{API}{path}'
    data = json.dumps(body).encode('utf-8') if body else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header('X-N8N-API-KEY', N8N_API_KEY)
    req.add_header('Content-Type', 'application/json')
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        body = e.read().decode('utf-8')
        return {'_error': e.code, '_body': body}

if not N8N_API_KEY:
    print('ERROR: N8N_API_KEY not set')
    sys.exit(1)

print(f'Connecting to {N8N_HOST}...')
test = api_request('GET', '/workflows?limit=5')
if '_error' in test:
    print(f'ERROR: Cannot reach n8n API: {test}')
    sys.exit(1)
print(f'Connected. Found {len(test.get("data", []))} workflows (first page).')

existing = api_request('GET', '/workflows?limit=100')
existing_by_name = {w['name']: w['id'] for w in existing.get('data', [])}

results = []
for wf_file in WORKFLOWS:
    wf_path = os.path.normpath(os.path.join(WORKFLOW_DIR, wf_file))
    if not os.path.exists(wf_path):
        print(f'  SKIP  {wf_file} — file not found at {wf_path}')
        continue

    with open(wf_path, encoding='utf-8') as f:
        wf_data = json.load(f)

    wf_clean = {k: v for k, v in wf_data.items() if k in ALLOWED_FIELDS}
    wf_name = wf_data.get('name', wf_file)

    existing_id = existing_by_name.get(wf_name)

    if existing_id:
        print(f'  UPDATE  {wf_name} (id: {existing_id})')
        result = api_request('PUT', f'/workflows/{existing_id}', wf_clean)
        if '_error' in result:
            print(f'    ERROR: {result["_body"][:300]}')
            results.append((wf_name, 'UPDATE_FAILED'))
            continue
        activate = api_request('PATCH', f'/workflows/{existing_id}', {'active': True})
        if '_error' in activate:
            print(f'    WARNING activate: {activate}')
        print(f'    OK — updated and activated')
        results.append((wf_name, 'UPDATED'))
    else:
        print(f'  CREATE  {wf_name}')
        result = api_request('POST', '/workflows', wf_clean)
        if '_error' in result:
            print(f'    ERROR: {result["_body"][:300]}')
            results.append((wf_name, 'CREATE_FAILED'))
            continue
        new_id = result.get('id', '')
        if new_id:
            activate = api_request('PATCH', f'/workflows/{new_id}', {'active': True})
            if '_error' in activate:
                print(f'    WARNING activate: {activate}')
        print(f'    OK — created (id: {new_id}) and activated')
        results.append((wf_name, 'CREATED'))

print('\n=== SUMMARY ===')
for name, status in results:
    icon = 'OK  ' if 'FAIL' not in status else 'FAIL'
    print(f'  [{icon}]  {status:15s}  {name}')

print('\n=== LIVE WORKFLOW STATUS ===')
final = api_request('GET', '/workflows?limit=100')
targets = ['Brain Dump', 'Daily Note', 'Overdue Task', 'Weekly', 'AI Brain', 'Article']
for w in final.get('data', []):
    name = w.get('name', '')
    if any(t in name for t in targets):
        status = 'ACTIVE  ' if w.get('active') else 'INACTIVE'
        print(f'  [{status}]  {name}')
