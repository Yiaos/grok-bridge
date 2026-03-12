#!/usr/bin/env bash
set -euo pipefail

BRIDGE_URL="${GROK_BRIDGE_URL:-http://127.0.0.1:19998}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO_DIR="$(cd "$SKILL_DIR/.." && pwd)"
START_SCRIPT="$REPO_DIR/scripts/start_chrome.sh"
TMP_HEALTH="/tmp/grok_bridge_skill_health.json"
TMP_START_LOG="/tmp/grok_bridge_skill_start.log"

check_health() {
  curl -fsS "$BRIDGE_URL/health" >"$TMP_HEALTH" || return 1
  cat "$TMP_HEALTH"
}

if check_health >/dev/null 2>&1; then
  cat "$TMP_HEALTH"
  exit 0
fi

bash "$START_SCRIPT" >"$TMP_START_LOG" 2>&1 || {
  cat "$TMP_START_LOG" >&2 || true
  exit 1
}

sleep 2

if check_health >/dev/null 2>&1; then
  cat "$TMP_HEALTH"
  exit 0
fi

echo "bridge_not_ready" >&2
cat "$TMP_START_LOG" >&2 || true
exit 2
