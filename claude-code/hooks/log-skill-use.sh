#!/bin/bash
# Tracks skill usage and posts an analytics event to the Fivetran webhook.
#
# Usage: log-skill-use.sh <manifest-path>
#   manifest-path: absolute path to the agent's plugin manifest
#                  (plugin.json for Claude Code / Codex, gemini-extension.json for Gemini)
#
# Fires on:
#   UserPromptSubmit / BeforeAgent — slash command invocations
#   PostToolUse / PostToolUseFailure — Skill tool calls (Claude Code, Codex)
#
# Always exits 0 — never blocks the agent's normal flow.

WEBHOOK_URL="${WEBHOOK_URL:-https://webhook.site/33268e96-b2de-4315-87e2-bcc794ce80e5}"
MAX_PAYLOAD_BYTES="${MAX_PAYLOAD_BYTES:-1048576}"
CONNECT_TIMEOUT_SECONDS="${CONNECT_TIMEOUT_SECONDS:-2}"
REQUEST_TIMEOUT_SECONDS="${REQUEST_TIMEOUT_SECONDS:-3}"

MANIFEST_JSON="${1:-}"

body=$(MANIFEST_JSON="$MANIFEST_JSON" MAX_PAYLOAD_BYTES="$MAX_PAYLOAD_BYTES" python3 -c "
import datetime, json, os, sys, uuid

allowed_skills = {'build-connector', 'test-connector', 'deploy-connector', 'evaluate-connector'}
max_payload_bytes = int(os.environ['MAX_PAYLOAD_BYTES'])
payload = sys.stdin.buffer.read(max_payload_bytes + 1)
if len(payload) > max_payload_bytes:
    sys.exit(0)

try:
    event = json.loads(payload.decode('utf-8') or '{}')
except Exception:
    sys.exit(0)

hook_event = event.get('hook_event_name')

if hook_event in ('UserPromptSubmit', 'BeforeAgent'):
    prompt = event.get('prompt') or ''
    if not prompt.startswith('/'):
        sys.exit(0)
    command_parts = prompt[1:].split(None, 1)
    if not command_parts:
        sys.exit(0)
    raw_skill = command_parts[0]
    if '/' in raw_skill:
        sys.exit(0)
elif hook_event in ('PostToolUse', 'PostToolUseFailure') and event.get('tool_name') == 'Skill':
    tool_input = event.get('tool_input') if isinstance(event.get('tool_input'), dict) else {}
    raw_skill = tool_input.get('skill') or ''
else:
    sys.exit(0)

skill = raw_skill.split(':')[-1]
if skill not in allowed_skills:
    sys.exit(0)

try:
    manifest = json.load(open(os.environ['MANIFEST_JSON']))
except Exception:
    manifest = {}

client_id = None
try:
    p = os.path.expanduser('~/.fivetran/client-id')
    if not os.path.exists(p):
        os.makedirs(os.path.dirname(p), exist_ok=True)
        tmp = f'{p}.{os.getpid()}.tmp'
        open(tmp, 'w').write(str(uuid.uuid4()))
        os.rename(tmp, p)
    client_id = open(p).read().strip() or None
except OSError:
    pass

print(json.dumps({
    'event': 'Skill Use',
    'plugin': manifest.get('name', 'unknown'),
    'version': manifest.get('version', 'unknown'),
    'skill': skill,
    'status': 'FAIL' if hook_event == 'PostToolUseFailure' else 'ok',
    'model': event.get('model'),
    'session_id': event.get('session_id'),
    'anonymous_id': client_id,
    'timestamp': datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
}))
")

if [[ -z "$body" ]]; then
  exit 0
fi

curl -s -o /dev/null -X POST "$WEBHOOK_URL" \
  --connect-timeout "$CONNECT_TIMEOUT_SECONDS" \
  --max-time "$REQUEST_TIMEOUT_SECONDS" \
  -H "Content-Type: application/json" \
  -d "$body" >/dev/null 2>&1 &

exit 0
