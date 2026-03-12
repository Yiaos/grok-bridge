#!/usr/bin/env bash
set -euo pipefail

CDP_PORT="${GROK_CDP_PORT:-9222}"
BRIDGE_PORT="${GROK_BRIDGE_PORT:-19998}"
BRIDGE_HOST="${GROK_BRIDGE_BIND_HOST:-127.0.0.1}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
VENV_DIR="$REPO_DIR/.venv"
PROFILE_DIR="${GROK_CHROME_PROFILE:-$REPO_DIR/.chrome-profile}"
LOG_FILE="${GROK_BRIDGE_LOG:-/tmp/grok_bridge.log}"
CHROME_BIN="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
PYTHON_BIN="$VENV_DIR/bin/python3"

ensure_python_env() {
  if [[ ! -x "$PYTHON_BIN" ]]; then
    echo "Creating Python venv in $VENV_DIR ..."
    python3 -m venv "$VENV_DIR"
  fi

  if ! "$PYTHON_BIN" - <<'PY' >/dev/null 2>&1
import importlib.util
raise SystemExit(0 if importlib.util.find_spec('websockets') else 1)
PY
  then
    echo "Installing Python dependency: websockets"
    "$PYTHON_BIN" -m pip install websockets >/dev/null
  fi
}

if [[ ! -x "$CHROME_BIN" ]]; then
  echo "❌ Chrome not found at: $CHROME_BIN" >&2
  exit 1
fi

mkdir -p "$PROFILE_DIR"
ensure_python_env

# Stop previous bridge instance only.
pkill -f "grok_bridge.py.*--port ${BRIDGE_PORT}" 2>/dev/null || true
pkill -f "grok_bridge.py --host ${BRIDGE_HOST} --port ${BRIDGE_PORT}" 2>/dev/null || true

# Start Chrome with dedicated profile if CDP is not already up.
if ! curl -fsS "http://127.0.0.1:${CDP_PORT}/json/version" >/dev/null 2>&1; then
  echo "Starting Chrome with CDP on :${CDP_PORT} ..."
  nohup "$CHROME_BIN" \
    --remote-debugging-port="$CDP_PORT" \
    --user-data-dir="$PROFILE_DIR" \
    --no-first-run \
    --no-default-browser-check \
    --new-window "https://grok.com" \
    >/tmp/grok_chrome_stdout.log 2>/tmp/grok_chrome_stderr.log &
  sleep 3
fi

if ! curl -fsS "http://127.0.0.1:${CDP_PORT}/json/version" >/dev/null 2>&1; then
  echo "❌ Failed to start Chrome CDP on port ${CDP_PORT}" >&2
  exit 1
fi

echo "Starting bridge on ${BRIDGE_HOST}:${BRIDGE_PORT} ..."
nohup "$PYTHON_BIN" "$SCRIPT_DIR/grok_bridge.py" --host "$BRIDGE_HOST" --port "$BRIDGE_PORT" --cdp-port "$CDP_PORT" \
  >"$LOG_FILE" 2>&1 &

echo "Bridge PID: $!"
sleep 2

if curl -fsS "http://${BRIDGE_HOST}:${BRIDGE_PORT}/health" >/dev/null 2>&1; then
  echo "✅ Bridge healthy on ${BRIDGE_HOST}:${BRIDGE_PORT}"
  echo "Now login in the Chrome window that opened (profile: $PROFILE_DIR)"
  echo "Test with:"
  echo "  curl http://${BRIDGE_HOST}:${BRIDGE_PORT}/health"
  echo "  bash $REPO_DIR/scripts/grok_chat.sh \"hello\""
else
  echo "❌ Bridge failed to start" >&2
  cat "$LOG_FILE" >&2 || true
  exit 1
fi
