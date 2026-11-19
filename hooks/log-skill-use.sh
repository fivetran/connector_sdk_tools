#!/bin/bash
# Tracks skill usage and posts an analytics event to the Fivetran webhook.
#
# Usage: log-skill-use.sh <manifest-path> [host]
#   manifest-path: absolute path to the agent's plugin manifest
#                  (plugin.json for Claude Code / Codex / Cursor,
#                  gemini-extension.json for Gemini)
#   host:          claude-code | codex | cursor | gemini (default: unknown).
#                  Selects where the one-time-notice marker lives and, for
#                  cursor, the JSON the host expects on stdout.
#
# Fires on:
#   UserPromptExpansion — slash command invocations (Claude Code); only the
#                         command name is read, never the prompt text
#   UserPromptSubmit / BeforeAgent / beforeSubmitPrompt — slash command
#                         invocations (Codex, Gemini, Cursor); only the leading
#                         "/" or "$" token of the prompt is read
#   PostToolUse / PostToolUseFailure — Skill tool calls (Claude Code, Codex)
#
# Opt-out: FIVETRAN_TELEMETRY_DISABLED=1 or DO_NOT_TRACK=1|true.
# First qualifying use shows a one-time notice and sends nothing; events start
# with the next qualifying use.
#
# Stdout is reserved for the notice JSON (and {"continue":true} for cursor).
# Always exits 0 — never blocks the agent's normal flow.

FIVETRAN_TELEMETRY_WEBHOOK_URL="${FIVETRAN_TELEMETRY_WEBHOOK_URL:-https://webhooks.fivetran.com/webhooks/e81a7476-32c0-44e7-8c6b-c3467f842b6f}"

HOST="${2:-unknown}"
[[ "$HOST" =~ ^[a-z-]+$ ]] || HOST="unknown"

# Cursor requires a JSON object on stdout; print {"continue":true} on every path
# that has not already printed one.
json_printed=0
finish() {
  if [[ "$HOST" == "cursor" && "$json_printed" == "0" ]]; then
    printf '{"continue":true}\n'
  fi
}
trap finish EXIT

# Opt-out: FIVETRAN_TELEMETRY_DISABLED=1, or the standard DO_NOT_TRACK=1 / true
# (trimmed, case-insensitive; same rule as the Fivetran CLIs). Checked before
# anything is read or sent.
[[ "${FIVETRAN_TELEMETRY_DISABLED:-0}" == "1" ]] && exit 0
do_not_track=$(printf '%s' "${DO_NOT_TRACK:-}" | tr '[:upper:]' '[:lower:]' | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//')
[[ "$do_not_track" == "1" || "$do_not_track" == "true" ]] && exit 0
MAX_PAYLOAD_BYTES="${MAX_PAYLOAD_BYTES:-1048576}"
CONNECT_TIMEOUT_SECONDS="${CONNECT_TIMEOUT_SECONDS:-2}"
REQUEST_TIMEOUT_SECONDS="${REQUEST_TIMEOUT_SECONDS:-3}"

MANIFEST_JSON="${1:-}"

body=$(MANIFEST_JSON="$MANIFEST_JSON" MAX_PAYLOAD_BYTES="$MAX_PAYLOAD_BYTES" python3 -c "
import datetime, json, os, sys

allowed_skills = {'build-connector', 'test-connector', 'deploy-connector', 'evaluate-connector', 'submit-to-community-catalog'}
max_payload_bytes = int(os.environ['MAX_PAYLOAD_BYTES'])
payload = sys.stdin.buffer.read(max_payload_bytes + 1)
if len(payload) > max_payload_bytes:
    sys.exit(0)

try:
    event = json.loads(payload.decode('utf-8') or '{}')
except Exception:
    sys.exit(0)

hook_event = event.get('hook_event_name')

if hook_event == 'UserPromptExpansion':
    raw_skill = event.get('command_name')
    if not isinstance(raw_skill, str):
        sys.exit(0)
elif hook_event in ('UserPromptSubmit', 'BeforeAgent', 'beforeSubmitPrompt'):
    # Keep only the first characters of the prompt: just enough for the leading command token.
    prompt_head = (event.get('prompt') or '').lstrip()[:128]
    if prompt_head.startswith('/'):
        command_parts = prompt_head[1:].split(None, 1)
    elif prompt_head.startswith('$'):
        command_parts = prompt_head.split(None, 1)
    else:
        sys.exit(0)
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

skill = raw_skill.split(':')[-1].lstrip('$').replace('_', '-')
if skill not in allowed_skills:
    sys.exit(0)

if hook_event in ('UserPromptExpansion', 'UserPromptSubmit', 'BeforeAgent', 'beforeSubmitPrompt'):
    status = 'started'
elif hook_event == 'PostToolUseFailure':
    status = 'fail'
else:
    status = 'ok'

try:
    with open(os.environ['MANIFEST_JSON'], 'r', encoding='utf-8') as f:
        manifest = json.load(f)
except Exception:
    manifest = {}

print(json.dumps({
    'event': 'Skill Use',
    'plugin': manifest.get('name', 'unknown'),
    'version': manifest.get('version', 'unknown'),
    'skill': skill,
    'status': status,
    'model': event.get('model'),
    'session_id': event.get('session_id') or event.get('conversation_id'),
    'timestamp': datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
}))
")

if [[ -z "$body" ]]; then
  exit 0
fi

# One-time notice. Shown the first time a qualifying event would be sent; nothing
# is sent on that run, so users can opt out before any event leaves their machine.
# The marker is per host. If it cannot be written, stay silent and send nothing.
if [[ "$HOST" == "claude-code" && -n "${CLAUDE_PLUGIN_DATA:-}" ]]; then
  marker_dir="$CLAUDE_PLUGIN_DATA"
else
  marker_dir="${HOME:-}/.fivetran/ai-plugins/$HOST"
fi
notice_marker="$marker_dir/telemetry-notice-shown"
if [[ ! -e "$notice_marker" ]]; then
  [[ -n "${HOME:-}" ]] || exit 0
  # Under an flock (released by the OS even if the hook is killed), the first hook prints the
  # notice and then writes the marker. Concurrent hooks wait, then see the marker and
  # send their event after the notice. Exit 3 = notice shown; any other failure = stay silent.
  HOST="$HOST" MARKER="$notice_marker" python3 -c "
import json, os
try:
    import fcntl
except ImportError:  # native Windows: no flock, a rare concurrent first run may show the notice twice
    fcntl = None
marker = os.environ['MARKER']
os.makedirs(os.path.dirname(marker), exist_ok=True)
with open(marker + '.lock', 'a') as lock:
    if fcntl:
        fcntl.flock(lock, fcntl.LOCK_EX)
    if os.path.exists(marker):
        raise SystemExit(0)
    # Keep this field list in step with the README and the docs page it links to.
    message = (
        'Fivetran Connector SDK plugin: telemetry notice\\n'
        'This plugin sends anonymous usage events when its skills run: skill name, plugin name and version, '
        'status, model, session ID and timestamp. No prompts, code, credentials or file contents are collected.\\n'
        'To opt out, set DO_NOT_TRACK=1 or FIVETRAN_TELEMETRY_DISABLED=1 in your shell profile.\\n'
        'Learn more: https://fivetran.com/docs/security-and-privacy/telemetry'
    )
    if os.environ['HOST'] == 'cursor':
        print(json.dumps({'continue': True, 'user_message': message}), flush=True)
    else:
        print(json.dumps({'systemMessage': message}), flush=True)
    try:
        open(marker, 'w').close()
    except OSError:
        pass  # notice was printed; it will show again next run
    raise SystemExit(3)
"
  case $? in
    0) ;;
    3) json_printed=1; exit 0 ;;
    *) exit 0 ;;
  esac
fi

curl -s -o /dev/null -X POST "$FIVETRAN_TELEMETRY_WEBHOOK_URL" \
  --connect-timeout "$CONNECT_TIMEOUT_SECONDS" \
  --max-time "$REQUEST_TIMEOUT_SECONDS" \
  -H "Content-Type: application/json" \
  -d "$body" 2>/dev/null &

exit 0
