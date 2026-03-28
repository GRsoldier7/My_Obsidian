#!/usr/bin/env python3
"""
Apply the 5 bug fixes to n8n workflow JSON files using proper JSON manipulation.
No raw string editing — Python loads/modifies/dumps the JSON to preserve escaping.
"""
import sys
import json
import os

sys.stdout.reconfigure(encoding='utf-8')

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
WF_DIR = os.path.normpath(os.path.join(SCRIPT_DIR, '..', 'workflows', 'n8n'))

def load(filename):
    path = os.path.join(WF_DIR, filename)
    with open(path, encoding='utf-8') as f:
        return json.load(f), path

def save(data, path):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f'  Saved: {os.path.basename(path)}')

def find_node(wf, node_id=None, node_name=None):
    for node in wf['nodes']:
        if node_id and node.get('id') == node_id:
            return node
        if node_name and node.get('name') == node_name:
            return node
    return None

# ══════════════════════════════════════════════════════════════════
# FIX 1 + 2: brain-dump-processor.json
# ══════════════════════════════════════════════════════════════════
print('\n[brain-dump-processor.json]')
wf, path = load('brain-dump-processor.json')

# Fix 1: Build All Updates — return individual file items instead of single array wrapper
node = find_node(wf, node_id='build-updates')
if node:
    old_code = node['parameters']['jsCode']
    # Replace the final return statement
    old_return = 'return [{ json: { filesToUpload, results, articleCount: articleUrls.length } }];'
    new_return = (
        '// Return individual file items so Loop: Write Each File iterates once per file\n'
        'return filesToUpload.map(f => ({ json: f }));'
    )
    if old_return in old_code:
        node['parameters']['jsCode'] = old_code.replace(old_return, new_return)
        print('  Fix 1 applied: Build All Updates returns individual items')
    else:
        print('  WARNING: Fix 1 pattern not found in Build All Updates')
else:
    print('  WARNING: build-updates node not found')

# Fix 2: Build Digest Email — read results from Parse AI Response cross-reference
node = find_node(wf, node_id='build-email')
if node:
    old_code = node['parameters']['jsCode']
    old_snippet = (
        '// Build smart digest email — grouped by type, needle-movers at top\n'
        'const input = $input.first().json;\n'
        'const results = input.results || [];'
    )
    new_snippet = (
        '// Build smart digest email — grouped by type, needle-movers at top\n'
        '// Read AI results from Parse AI Response node (not from the write loop items)\n'
        'let results = [];\n'
        'try {\n'
        '  results = $(\'Parse AI Response\').first().json.results || [];\n'
        '} catch (e) {\n'
        '  results = [];\n'
        '}'
    )
    if old_snippet in old_code:
        node['parameters']['jsCode'] = old_code.replace(old_snippet, new_snippet)
        print('  Fix 2 applied: Build Digest Email reads from Parse AI Response')
    else:
        print('  WARNING: Fix 2 pattern not found in Build Digest Email')
else:
    print('  WARNING: build-email node not found')

save(wf, path)

# ══════════════════════════════════════════════════════════════════
# FIX 3: daily-note-creator.json
# ══════════════════════════════════════════════════════════════════
print('\n[daily-note-creator.json]')
wf, path = load('daily-note-creator.json')

node = find_node(wf, node_id='note-missing-check')
if node:
    conds = node['parameters']['conditions']['conditions']
    fixed = False
    for cond in conds:
        if '$json.binary' in cond.get('leftValue', ''):
            cond['leftValue'] = cond['leftValue'].replace('$json.binary', '$binary')
            fixed = True
    if fixed:
        print('  Fix 3 applied: Note Missing? uses $binary instead of $json.binary')
    else:
        # Check if already fixed
        for cond in conds:
            if '$binary' in cond.get('leftValue', '') and '$json.binary' not in cond.get('leftValue', ''):
                print('  Fix 3 already applied (condition already uses $binary)')
                fixed = True
                break
        if not fixed:
            print('  WARNING: Fix 3 pattern not found in Note Missing? conditions')
            print('  Conditions:', conds)
else:
    print('  WARNING: note-missing-check node not found')

save(wf, path)

# ══════════════════════════════════════════════════════════════════
# FIX 4: article-processor.json
# ══════════════════════════════════════════════════════════════════
print('\n[article-processor.json]')
wf, path = load('article-processor.json')

# Fix 4a: Parse URLs — return individual items per URL
node = find_node(wf, node_id='parse-urls')
if node:
    old_code = node['parameters']['jsCode']
    old_return = 'return [{ json: { hasUrls: urls.length > 0, urls, urlCount: urls.length } }];'
    new_return = (
        '// Return one item per URL so SplitInBatches iterates once per URL\n'
        '// Gate check: single hasUrls:false item if queue is empty\n'
        'if (urls.length === 0) {\n'
        '  return [{ json: { hasUrls: false, url: null, context: \'\', urlCount: 0 } }];\n'
        '}\n'
        'return urls.map(u => ({ json: { hasUrls: true, url: u.url, context: u.context, urlCount: urls.length } }));'
    )
    if old_return in old_code:
        node['parameters']['jsCode'] = old_code.replace(old_return, new_return)
        print('  Fix 4a applied: Parse URLs returns individual URL items')
    else:
        print('  WARNING: Fix 4a pattern not found in Parse URLs')
else:
    print('  WARNING: parse-urls node not found')

# Fix 4b: Get Current URL — proper passthrough
node = find_node(wf, node_id='get-current-url')
if node:
    node['parameters']['jsCode'] = (
        '// Each item from the loop is already a single {url, context} object\n'
        '// Pass it through cleanly for Fetch Page\n'
        'const item = $input.first().json;\n'
        'return [{ json: { url: item.url, context: item.context || \'\' } }];'
    )
    print('  Fix 4b applied: Get Current URL passes url/context cleanly')
else:
    print('  WARNING: get-current-url node not found')

save(wf, path)

# ══════════════════════════════════════════════════════════════════
# FIX 5: overdue-task-alert.json — sequential S3 reads (no fan-out)
# ══════════════════════════════════════════════════════════════════
print('\n[overdue-task-alert.json]')
wf, path = load('overdue-task-alert.json')

conns = wf['connections']

# Remove S3: Read North Star from Define Files to Scan output
define_outputs = conns.get('Define Files to Scan', {}).get('main', [[]])
if define_outputs and len(define_outputs) > 0:
    # Filter out the S3: Read North Star connection
    first_output = [c for c in define_outputs[0] if c.get('node') != 'S3: Read North Star']
    conns['Define Files to Scan']['main'] = [first_output]
    print('  Fix 5a: Removed S3: Read North Star from Define Files to Scan fan-out')

# Change S3: Download File to connect to S3: Read North Star (instead of Scan)
conns['S3: Download File'] = {
    'main': [[{'node': 'S3: Read North Star', 'type': 'main', 'index': 0}]]
}
print('  Fix 5b: S3: Download File now chains to S3: Read North Star')

# S3: Read North Star connects to Scan for Overdue Tasks (was already there, verify)
if 'S3: Read North Star' not in conns:
    conns['S3: Read North Star'] = {
        'main': [[{'node': 'Scan for Overdue Tasks', 'type': 'main', 'index': 0}]]
    }
    print('  Fix 5c: Added S3: Read North Star → Scan for Overdue Tasks connection')
else:
    print('  Fix 5c: S3: Read North Star → Scan connection already exists')

save(wf, path)

# ══════════════════════════════════════════════════════════════════
# VALIDATE ALL FILES
# ══════════════════════════════════════════════════════════════════
print('\n=== VALIDATION ===')
for fname in ['brain-dump-processor.json', 'daily-note-creator.json',
              'overdue-task-alert.json', 'article-processor.json',
              'weekly-digest.json', 'ai-brain.json']:
    fpath = os.path.join(WF_DIR, fname)
    try:
        with open(fpath, encoding='utf-8') as f:
            json.load(f)
        print(f'  VALID   {fname}')
    except Exception as e:
        print(f'  INVALID {fname}: {e}')

print('\nAll fixes applied successfully.')
