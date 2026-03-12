#!/usr/bin/env bash
# grok_chat.sh v4 — CLI wrapper over local CDP bridge
set -euo pipefail

PROMPT="${1:?Usage: grok_chat.sh 'question' [--timeout 60]}"
TIMEOUT=120
shift || true
while [[ $# -gt 0 ]]; do
  case "$1" in
    --timeout) TIMEOUT="$2"; shift 2 ;;
    *) shift ;;
  esac
done

BASE_URL="${GROK_BRIDGE_URL:-http://127.0.0.1:19998}"

python3 - <<'PY' "$BASE_URL" "$PROMPT" "$TIMEOUT"
import json, sys, urllib.request
base, prompt, timeout = sys.argv[1], sys.argv[2], int(sys.argv[3])
req = urllib.request.Request(
    base + '/chat',
    data=json.dumps({'prompt': prompt, 'timeout': timeout}).encode(),
    headers={'Content-Type': 'application/json'},
    method='POST',
)
with urllib.request.urlopen(req, timeout=timeout + 30) as r:
    data = json.loads(r.read().decode())
if data.get('status') not in ('ok', 'timeout'):
    raise SystemExit(data.get('error') or data)
print(data.get('response', ''))
PY
