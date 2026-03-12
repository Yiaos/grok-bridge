---
name: grok-bridge
description: Use the local Grok bridge in Chrome/CDP when the user explicitly asks to use Grok, asks for Grok's opinion/answer, says 用 grok / 让 grok 回答 / ask Grok, or wants a side-by-side comparison with Grok.
user-invocable: false
---

# Grok Bridge

Use this skill when the user explicitly wants **Grok** involved.

## Trigger examples

- `用 grok 回答这个问题`
- `让 grok 看看`
- `ask Grok this`
- `give me Grok's take`
- `用 grok 和你各答一版`
- `compare your answer with Grok`

Do **not** trigger just because the topic mentions Grok. Trigger when the user wants a Grok-backed answer.

## Workflow

1. Ensure the local bridge is up:
   - Run `scripts/ensure_bridge.sh`
2. If bridge startup/login is needed:
   - Tell the user to log into the Chrome window opened by the bridge
   - Do not guess a Grok answer without actually calling it
3. Call Grok:
   - Run `python3 scripts/ask_grok.py --prompt '<prompt>' --timeout <seconds>`
4. Return the result in normal assistant voice

## Paths

- Workspace entry symlink: `/Users/iaos/.openclaw/workspace/skills/grok-bridge`
- Canonical skill dir (repo-managed): `/Users/iaos/.openclaw/workspace/tools/grok-bridge/skill`
- Bridge repo: `/Users/iaos/.openclaw/workspace/tools/grok-bridge`
- Bridge URL default: `http://127.0.0.1:19998`

## Response rules

- If user asked only for Grok's answer: return Grok's answer clearly labeled if needed
- If user asked for comparison: separate **my take** and **Grok's take**
- If the bridge returns an error, report the real failure briefly
- Keep it local-only; do not suggest exposing the bridge publicly

## Useful commands

Health:

```bash
bash scripts/ensure_bridge.sh
```

Ask Grok:

```bash
python3 scripts/ask_grok.py --prompt "Reply with exactly: OK" --timeout 90
```
