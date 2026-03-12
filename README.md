# 🌉 grok-bridge v4 (CDP)

Turn a logged-in **grok.com** Chrome session into a local REST API + CLI tool.

## How it works

```text
Your Terminal/Script -> grok_bridge.py -> Chrome DevTools Protocol -> grok.com tab
```

This version uses **Chrome CDP**, not Safari AppleScript.

## Quick Start

### 1) Start Chrome + bridge

```bash
bash scripts/start_chrome.sh
```

This will:
- create a local Python `.venv` if needed
- install `websockets`
- start Chrome with `--remote-debugging-port`
- use a dedicated Chrome profile under `.chrome-profile`
- start the local bridge on `127.0.0.1:19998`
- keep tab activation **off by default**, so bridge calls do not intentionally bring the Grok tab to the foreground

### 2) Login once

A Chrome window will open to `https://grok.com`.
Login there manually.

If you explicitly want bridge calls to refocus the Grok tab, start with:

```bash
GROK_ACTIVATE_TAB=1 bash scripts/start_chrome.sh
```

### 3) Use the API

```bash
curl -X POST http://127.0.0.1:19998/chat \
  -H "Content-Type: application/json" \
  -d '{"prompt":"Reply with exactly: OK","timeout":90}'

curl http://127.0.0.1:19998/health
curl http://127.0.0.1:19998/history
curl -X POST http://127.0.0.1:19998/new
```

### 4) Use the CLI

```bash
bash scripts/grok_chat.sh "Explain quantum tunneling" --timeout 120
```

## API Endpoints

- `POST /chat` — send prompt and wait for response
- `POST /new` — open a new `grok.com` tab
- `GET /health` — CDP/browser health
- `GET /history` — current page text + extracted message candidates

## Defaults

- Bridge bind host: `127.0.0.1`
- Bridge port: `19998`
- Chrome CDP port: `9222`
- Chrome profile dir: `./.chrome-profile`

## Notes

- This is still **web automation**, not an official API.
- DOM changes on grok.com can break selectors/extraction.
- Keep it local. Do **not** expose the bridge publicly unless you add your own auth layer.

## Requirements

- macOS
- Google Chrome
- Python 3.8+
- `websockets` Python package (auto-installed by `start_chrome.sh`)

## License

MIT
