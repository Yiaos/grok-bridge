#!/bin/bash
# grok_chat.sh v2 — VPS → SSH Mac → Safari JS injection → Grok
# Usage: bash grok_chat.sh "your question" [--timeout 60] [--screenshot]
set -e

PROMPT="${1:?Usage: grok_chat.sh 'question' [--timeout 60] [--screenshot]}"
TIMEOUT=60
SCREENSHOT=false
shift || true
while [[ $# -gt 0 ]]; do
  case "$1" in
    --timeout) TIMEOUT="$2"; shift 2 ;;
    --screenshot) SCREENSHOT=true; shift ;;
    *) shift ;;
  esac
done

MAC="ssh -o ConnectTimeout=5 -o BatchMode=yes root@100.92.28.97"

# Helper: run JS in Safari Grok tab
run_js() {
  local js="$1"
  $MAC "osascript -e 'tell application \"Safari\" to do JavaScript \"${js}\" in current tab of window 1'" 2>/dev/null
}

# Helper: run AppleScript
run_as() {
  $MAC "osascript -e '$1'" 2>/dev/null
}

# 1. Navigate to new conversation
echo "[grok] New conversation..." >&2
run_as 'tell application "Safari"
  repeat with t in tabs of window 1
    if URL of t contains "grok.com" then
      set current tab of window 1 to t
      set URL of t to "https://grok.com/"
      exit repeat
    end if
  end repeat
end tell'
sleep 4

# 2. Inject prompt via base64
B64=$(printf '%s' "$PROMPT" | base64 | tr -d '\n')
echo "[grok] Injecting (${#PROMPT} chars)..." >&2

INJECT_RESULT=$(run_js "
(function(){
  var text = atob('${B64}');
  var ta = document.querySelector('textarea');
  if (!ta) return 'error:no-textarea';
  ta.focus();
  var s = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype,'value').set;
  s.call(ta, text);
  ta.dispatchEvent(new Event('input',{bubbles:true}));
  ta.dispatchEvent(new Event('change',{bubbles:true}));
  return 'ok';
})()
")
echo "[grok] Inject: $INJECT_RESULT" >&2

sleep 1

# 3. Submit via Enter key event
echo "[grok] Submitting..." >&2
run_js "
(function(){
  var ta = document.querySelector('textarea');
  if (!ta) return;
  ta.dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',code:'Enter',keyCode:13,which:13,bubbles:true,cancelable:true}));
})()
"

# 4. Wait for response
echo "[grok] Waiting (${TIMEOUT}s timeout)..." >&2
sleep 8

# Find the conversation in history and navigate to it
CONV_URL=$($MAC "osascript -e 'tell application \"Safari\" to URL of current tab of window 1'" 2>/dev/null)
if [[ "$CONV_URL" == "https://grok.com/" ]]; then
  # Still on homepage — click into the new conversation from history
  echo "[grok] Navigating to conversation..." >&2
  run_js "
(function(){
  var links = document.querySelectorAll('a');
  for (var i=0; i<links.length; i++) {
    var href = links[i].getAttribute('href') || '';
    if (href.indexOf('/chat/') === 0 || href.indexOf('/c/') === 0) {
      links[i].click();
      return 'clicked';
    }
  }
  return 'no-link';
})()
"
  sleep 3
fi

# 5. Poll for response completion
PREV=""
STABLE=0
for ((i=1; i<=TIMEOUT; i++)); do
  sleep 2
  CURRENT=$(run_js "
(function(){
  var blocks = document.querySelectorAll('div[class*=message], article, div[data-message-author-role]');
  if (blocks.length === 0) {
    // Fallback: get all text after the question
    var body = document.body.innerText;
    var lines = body.split('\\\\n');
    return lines.slice(-20).join('\\\\n');
  }
  var last = blocks[blocks.length-1];
  return last.innerText || '';
})()
" || echo "")

  if [[ -n "$CURRENT" && ${#CURRENT} -gt 5 && "$CURRENT" == "$PREV" ]]; then
    STABLE=$((STABLE + 1))
    if [[ $STABLE -ge 2 ]]; then
      echo "[grok] Done (${i}×2s)" >&2
      break
    fi
  else
    STABLE=0
  fi
  PREV="$CURRENT"

  if ((i % 5 == 0)); then
    echo "[grok] Polling... ${i}×2s" >&2
  fi
done

# 6. Extract response
RESPONSE=$($MAC 'osascript << "ENDAS"
tell application "Safari"
  set pageText to do JavaScript "document.body.innerText" in current tab of window 1
end tell
return pageText
ENDAS' 2>/dev/null)

# Parse: extract Grok's answer (text after the user's question)
echo "$RESPONSE" | awk -v q="$PROMPT" '
  BEGIN { found=0; printing=0 }
  found && /^[[:space:]]*$/ && !printing { next }
  found && !printing { printing=1 }
  printing { print }
  index($0, substr(q,1,30)) > 0 { found=1 }
' | head -100

# 7. Optional screenshot
if $SCREENSHOT; then
  TS=$(date +%s)
  SHOT="/tmp/grok_${TS}.jpg"
  $MAC "/usr/sbin/screencapture -x -t jpg $SHOT && cat $SHOT" > "/tmp/grok_${TS}.jpg" 2>/dev/null
  echo "[grok] Screenshot: /tmp/grok_${TS}.jpg" >&2
fi
