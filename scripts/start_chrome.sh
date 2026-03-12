#!/usr/bin/env bash
set -euo pipefail

CDP_PORT="${GROK_CDP_PORT:-9222}"
BRIDGE_PORT="${GROK_BRIDGE_PORT:-19998}"
BRIDGE_HOST="${GROK_BRIDGE_BIND_HOST:-127.0.0.1}"
GROK_CHROME_MODE="${GROK_CHROME_MODE:-hidden}"
GROK_START_URL="${GROK_START_URL:-https://grok.com}"
GROK_ACTIVATE_TAB="${GROK_ACTIVATE_TAB:-0}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
VENV_DIR="$REPO_DIR/.venv"
PROFILE_DIR="${GROK_CHROME_PROFILE:-$REPO_DIR/.chrome-profile}"
LOG_FILE="${GROK_BRIDGE_LOG:-/tmp/grok_bridge.log}"
CHROME_STDOUT_LOG="${GROK_CHROME_STDOUT_LOG:-/tmp/grok_chrome_stdout.log}"
CHROME_STDERR_LOG="${GROK_CHROME_STDERR_LOG:-/tmp/grok_chrome_stderr.log}"
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

launch_chrome() {
  local chrome_args=(
    "--remote-debugging-port=${CDP_PORT}"
    "--user-data-dir=${PROFILE_DIR}"
    --no-first-run
    --no-default-browser-check
  )

  case "$GROK_CHROME_MODE" in
    headless)
      chrome_args+=(
        --headless=new
        --disable-gpu
        "$GROK_START_URL"
      )
      nohup "$CHROME_BIN" "${chrome_args[@]}" >"$CHROME_STDOUT_LOG" 2>"$CHROME_STDERR_LOG" &
      ;;
    hidden)
      chrome_args+=("$GROK_START_URL")
      nohup "$CHROME_BIN" "${chrome_args[@]}" >"$CHROME_STDOUT_LOG" 2>"$CHROME_STDERR_LOG" &
      sleep 1
      osascript -e 'tell application "Google Chrome" to hide' >/dev/null 2>&1 || true
      ;;
    windowed)
      chrome_args+=(
        --new-window
        "$GROK_START_URL"
      )
      nohup "$CHROME_BIN" "${chrome_args[@]}" >"$CHROME_STDOUT_LOG" 2>"$CHROME_STDERR_LOG" &
      ;;
    *)
      echo "❌ Unsupported GROK_CHROME_MODE: $GROK_CHROME_MODE (expected: hidden|headless|windowed)" >&2
      exit 1
      ;;
  esac
}

# Start Chrome with dedicated profile if CDP is not already up.
if ! curl -fsS "http://127.0.0.1:${CDP_PORT}/json/version" >/dev/null 2>&1; then
  echo "Starting Chrome with CDP on :${CDP_PORT} (mode=${GROK_CHROME_MODE}) ..."
  launch_chrome
  sleep 3
fi

if ! curl -fsS "http://127.0.0.1:${CDP_PORT}/json/version" >/dev/null 2>&1; then
  echo "❌ Failed to start Chrome CDP on port ${CDP_PORT}" >&2
  exit 1
fi

bridge_args=(
  --host "$BRIDGE_HOST"
  --port "$BRIDGE_PORT"
  --cdp-port "$CDP_PORT"
)
if [[ "$GROK_ACTIVATE_TAB" == "1" ]]; then
  bridge_args+=(--activate-tab)
fi

echo "Starting bridge on ${BRIDGE_HOST}:${BRIDGE_PORT} ..."
nohup "$PYTHON_BIN" "$SCRIPT_DIR/grok_bridge.py" "${bridge_args[@]}" \
  >"$LOG_FILE" 2>&1 &

echo "Bridge PID: $!"
sleep 2

if curl -fsS "http://${BRIDGE_HOST}:${BRIDGE_PORT}/health" >/dev/null 2>&1; then
  echo "✅ Bridge healthy on ${BRIDGE_HOST}:${BRIDGE_PORT}"
  case "$GROK_CHROME_MODE" in
    headless)
      echo "Chrome is running headless with profile: $PROFILE_DIR"
      echo "Warning: grok.com may still present anti-bot verification in headless mode."
      echo "Need a visible fallback? Run: GROK_CHROME_MODE=windowed bash $REPO_DIR/scripts/start_chrome.sh"
      ;;
    hidden)
      echo "Chrome is running hidden with profile: $PROFILE_DIR"
      echo "Bridge foreground activation: $([[ "$GROK_ACTIVATE_TAB" == "1" ]] && echo on || echo off)"
      echo "Need a visible login/debug session? Run: GROK_CHROME_MODE=windowed bash $REPO_DIR/scripts/start_chrome.sh"
      ;;
    windowed)
      echo "Now login in the Chrome window that opened (profile: $PROFILE_DIR)"
      echo "Bridge foreground activation: $([[ "$GROK_ACTIVATE_TAB" == "1" ]] && echo on || echo off)"
      ;;
  esac
  echo "Test with:"
  echo "  curl http://${BRIDGE_HOST}:${BRIDGE_PORT}/health"
  echo "  bash $REPO_DIR/scripts/grok_chat.sh \"hello\""
else
  echo "❌ Bridge failed to start" >&2
  cat "$LOG_FILE" >&2 || true
  exit 1
fi
