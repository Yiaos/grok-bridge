#!/usr/bin/env python3
"""
grok_bridge.py v4 — Talk to Grok via Chrome CDP (macOS)

Architecture:
  HTTP client -> grok_bridge.py -> Chrome DevTools Protocol -> grok.com tab

Why this version:
  - No Safari / AppleScript dependency
  - No front-window requirement
  - More reliable input + send path via CDP
  - Safer default bind host: 127.0.0.1

Usage:
  python3 scripts/grok_bridge.py --host 127.0.0.1 --port 19998 --cdp-port 9222

Requirements:
  - Chrome started with --remote-debugging-port=9222
  - Logged into grok.com in that Chrome profile
  - Python package: websockets
"""

import argparse
import asyncio
import json
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn

try:
    import websockets
except ImportError as e:
    raise SystemExit(
        "Missing dependency: websockets\n"
        "Install with: python3 -m pip install websockets\n"
        "Or use: bash scripts/start_chrome.sh\n"
    ) from e


GROK_URL = 'https://grok.com/'
VERSION = 'v4-cdp'
INPUT_SELECTORS = [
    'textarea',
    'div[contenteditable="true"]',
    '[role="textbox"]',
    '[data-testid="text-input"]',
    '[data-lexical-editor="true"]',
]
SEND_SELECTORS = [
    'button[aria-label="Send"]',
    'button[aria-label*="Send"]',
    'button[data-testid="send-button"]',
    'button[type="submit"]',
]
UI_NOISE_LINES = {
    '切换侧边栏', '搜索', '⌘K', '新建聊天', '⌘J', '语音', 'Imagine', '项目', '新建项目',
    '历史记录', '查看全部', '分享', '附件', '附件附件', '快速模式', 'Fast', 'Auto',
    'Think', 'Think Harder', 'DeepSearch', 'Grok', 'New conversation', 'Search', 'Projects',
    'History', 'Share', 'Attach', 'Ask anything', 'Private', 'Upgrade to SuperGrok',
}


class GrokBridge:
    def __init__(self, cdp_port=9222):
        self.cdp_port = cdp_port
        self.lock = threading.Lock()

    def _http_json(self, path, method='GET', timeout=5):
        req = urllib.request.Request(f'http://127.0.0.1:{self.cdp_port}{path}', method=method)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode())

    def _targets(self):
        return self._http_json('/json/list', timeout=5)

    def _grok_targets(self):
        targets = []
        for t in self._targets():
            if t.get('type') != 'page':
                continue
            url = (t.get('url') or '').lower()
            if 'grok.com' in url:
                targets.append(t)
        return targets

    def _pick_target(self):
        targets = self._grok_targets()
        if not targets:
            return None

        def score(t):
            url = (t.get('url') or '').lower()
            title = (t.get('title') or '').lower()
            s = 0
            if url.startswith('https://grok.com'):
                s += 5
            if '/chat' in url or url.rstrip('/') == 'https://grok.com':
                s += 3
            if 'grok' in title:
                s += 1
            return s

        targets.sort(key=score, reverse=True)
        return targets[0]

    def _open_grok_tab(self):
        quoted = urllib.parse.quote(GROK_URL, safe='')
        last_err = None
        for method in ('PUT', 'GET'):
            try:
                req = urllib.request.Request(
                    f'http://127.0.0.1:{self.cdp_port}/json/new?{quoted}',
                    method=method,
                )
                with urllib.request.urlopen(req, timeout=5) as r:
                    data = json.loads(r.read().decode())
                return data
            except Exception as e:
                last_err = e
        raise RuntimeError(f'failed to open grok tab via CDP: {last_err}')

    def _activate_target(self, target_id):
        try:
            urllib.request.urlopen(
                f'http://127.0.0.1:{self.cdp_port}/json/activate/{target_id}', timeout=3
            ).read()
        except Exception:
            pass

    def _ws_url(self, ensure=False):
        target = self._pick_target()
        if not target and ensure:
            self._open_grok_tab()
            time.sleep(2)
            target = self._pick_target()
        if not target:
            raise RuntimeError('no grok.com tab found; start Chrome CDP and login first')
        self._activate_target(target.get('id'))
        ws = target.get('webSocketDebuggerUrl')
        if not ws:
            raise RuntimeError('target missing webSocketDebuggerUrl')
        return ws

    async def _eval(self, ws, mid, expression, timeout=30):
        mid[0] += 1
        cid = mid[0]
        await ws.send(json.dumps({
            'id': cid,
            'method': 'Runtime.evaluate',
            'params': {
                'expression': expression,
                'returnByValue': True,
                'awaitPromise': True,
            },
        }))
        while True:
            raw = await asyncio.wait_for(ws.recv(), timeout=timeout)
            msg = json.loads(raw)
            if msg.get('id') != cid:
                continue
            result = msg.get('result', {})
            if 'exceptionDetails' in result:
                text = result['exceptionDetails'].get('text') or 'Runtime.evaluate failed'
                raise RuntimeError(text)
            value = result.get('result', {})
            return value.get('value', value.get('description', ''))

    async def _key(self, ws, mid, key='Enter', code='Enter', key_code=13):
        for typ in ('keyDown', 'keyUp'):
            mid[0] += 1
            cid = mid[0]
            await ws.send(json.dumps({
                'id': cid,
                'method': 'Input.dispatchKeyEvent',
                'params': {
                    'type': typ,
                    'key': key,
                    'code': code,
                    'windowsVirtualKeyCode': key_code,
                    'nativeVirtualKeyCode': key_code,
                },
            }))
            while True:
                raw = await asyncio.wait_for(ws.recv(), timeout=10)
                msg = json.loads(raw)
                if msg.get('id') == cid:
                    break

    async def _wait_ready(self, ws, mid, timeout=30):
        selectors_json = json.dumps(INPUT_SELECTORS)
        start = time.time()
        while time.time() - start < timeout:
            selector = await self._eval(ws, mid, f"""(() => {{
                const sels = {selectors_json};
                for (const sel of sels) {{
                    const el = document.querySelector(sel);
                    if (!el) continue;
                    const visible = !!(el.offsetParent || el.getClientRects().length);
                    if (visible) return sel;
                }}
                return '';
            }})()""")
            if selector:
                return selector
            await asyncio.sleep(0.5)
        return None

    async def _composer_text(self, ws, mid, selector=None):
        selector_json = json.dumps(selector) if selector else 'null'
        selectors_json = json.dumps(INPUT_SELECTORS)
        return await self._eval(ws, mid, f"""(() => {{
            const primary = {selector_json};
            const sels = primary ? [primary, ...{selectors_json}.filter(x => x !== primary)] : {selectors_json};
            for (const sel of sels) {{
                const el = document.querySelector(sel);
                if (!el) continue;
                const t = (el.value ?? el.innerText ?? el.textContent ?? '').trim();
                if (t || sel === primary) return t;
            }}
            return '';
        }})()""")

    async def _message_candidates(self, ws, mid):
        data = await self._eval(ws, mid, r'''(() => {
            const sels = [
                'main article',
                'article',
                '[data-testid*="message"]',
                '[data-testid*="conversation"]',
                '[role="article"]',
                '[role="listitem"]'
            ];
            const seen = new Set();
            const out = [];
            for (const sel of sels) {
                for (const el of document.querySelectorAll(sel)) {
                    if (!el) continue;
                    const visible = !!(el.offsetParent || el.getClientRects().length);
                    if (!visible) continue;
                    const txt = (el.innerText || el.textContent || '').trim();
                    if (!txt || txt.length < 2) continue;
                    if (txt.length > 12000) continue;
                    if (seen.has(txt)) continue;
                    seen.add(txt);
                    out.push(txt);
                }
            }
            return out.slice(-30);
        })()''')
        return data if isinstance(data, list) else []

    async def _body_text(self, ws, mid):
        return await self._eval(ws, mid, 'document.body.innerText', timeout=20)

    async def _insert_prompt(self, ws, mid, prompt, selector):
        text_json = json.dumps(prompt)
        sel_json = json.dumps(selector)
        return await self._eval(ws, mid, f"""(() => {{
            const text = {text_json};
            const el = document.querySelector({sel_json});
            if (!el) return 'NO_INPUT';
            el.focus();
            if (el.isContentEditable) {{
                const range = document.createRange();
                range.selectNodeContents(el);
                const sel = window.getSelection();
                sel.removeAllRanges();
                sel.addRange(range);
                document.execCommand('delete');
                document.execCommand('insertText', false, text);
                const cur = (el.innerText || el.textContent || '').trim();
                return cur.includes(text.slice(0, Math.min(20, text.length))) ? 'OK' : 'TYPE_FAIL';
            }}
            if ('value' in el) {{
                el.value = '';
                el.dispatchEvent(new Event('input', {{ bubbles: true }}));
                el.value = text;
                el.dispatchEvent(new Event('input', {{ bubbles: true }}));
                return (el.value || '').includes(text.slice(0, Math.min(20, text.length))) ? 'OK' : 'TYPE_FAIL';
            }}
            el.textContent = text;
            el.dispatchEvent(new Event('input', {{ bubbles: true }}));
            const cur = (el.innerText || el.textContent || '').trim();
            return cur.includes(text.slice(0, Math.min(20, text.length))) ? 'OK' : 'TYPE_FAIL';
        }})()""")

    async def _click_send_button(self, ws, mid):
        selectors_json = json.dumps(SEND_SELECTORS)
        return await self._eval(ws, mid, f"""(() => {{
            const sels = {selectors_json};
            for (const sel of sels) {{
                const btn = document.querySelector(sel);
                if (btn && !btn.disabled) {{
                    btn.click();
                    return 'OK_SELECTOR';
                }}
            }}
            const btns = [...document.querySelectorAll('button')];
            const textBtn = btns.find(b => !b.disabled && /^(send|发送)$/i.test((b.textContent || b.getAttribute('aria-label') || '').trim()));
            if (textBtn) {{
                textBtn.click();
                return 'OK_TEXT';
            }}
            const ariaBtn = btns.find(b => !b.disabled && /send/i.test(b.getAttribute('aria-label') || ''));
            if (ariaBtn) {{
                ariaBtn.click();
                return 'OK_ARIA';
            }}
            return 'NO_BUTTON';
        }})()""")

    async def _send_prompt(self, ws, mid, prompt, selector):
        result = await self._click_send_button(ws, mid)
        await asyncio.sleep(0.8)
        composer = await self._composer_text(ws, mid, selector)
        if not composer or prompt[:20] not in composer:
            return {'ok': True, 'method': str(result)}

        await self._eval(ws, mid, f"document.querySelector({json.dumps(selector)})?.focus()")
        await asyncio.sleep(0.2)
        await self._key(ws, mid, 'Enter', 'Enter', 13)
        await asyncio.sleep(0.8)
        composer = await self._composer_text(ws, mid, selector)
        if not composer or prompt[:20] not in composer:
            return {'ok': True, 'method': 'CDP_ENTER'}
        return {'ok': False, 'method': str(result), 'composer': composer[:200]}

    def _clean_text(self, text):
        text = (text or '').replace('\r', '')
        text = re.sub(r'\n{3,}', '\n\n', text)
        lines = []
        for raw in text.split('\n'):
            line = raw.strip()
            if not line:
                if lines and lines[-1] != '':
                    lines.append('')
                continue
            if line in UI_NOISE_LINES:
                continue
            if re.fullmatch(r'\d+(\.\d+)?\s*(ms|s)', line, flags=re.I):
                continue
            if re.fullmatch(r'\d+\s+sources?', line, flags=re.I):
                continue
            if re.fullmatch(r'(Good|Bad|Copy|Share|Compare|Explain|Toggle|Like|Dislike)', line, flags=re.I):
                continue
            if any(key in line for key in ['首分块时延', '首 token 时延', '首个摘要令牌的时间', '响应时间']):
                continue
            lines.append(line)
        while lines and lines[-1] == '':
            lines.pop()
        return '\n'.join(lines).strip()

    def _extract_from_messages(self, messages, prompt):
        if not messages:
            return ''
        prompt_prefix = prompt[:80].strip()
        hit = -1
        for i, msg in enumerate(messages):
            if prompt_prefix and prompt_prefix in msg:
                hit = i
        if hit >= 0 and hit + 1 < len(messages):
            return self._clean_text(messages[hit + 1])
        tail = messages[-1]
        if prompt_prefix and prompt_prefix in tail and len(messages) >= 2:
            return self._clean_text(messages[-2])
        return self._clean_text(tail)

    def _extract_from_body(self, body, prompt):
        body = body or ''
        marker = prompt[:80]
        if marker and marker in body:
            after = body.split(marker, 1)[-1]
        else:
            after = body
        return self._clean_text(after)

    def _extract_response(self, messages, body, prompt):
        msg_resp = self._extract_from_messages(messages, prompt)
        if msg_resp and msg_resp != self._clean_text(prompt):
            return msg_resp
        return self._extract_from_body(body, prompt)

    async def _history_async(self):
        async with websockets.connect(self._ws_url(ensure=False), max_size=10 * 1024 * 1024, open_timeout=10) as ws:
            mid = [0]
            body = str(await self._body_text(ws, mid))
            messages = await self._message_candidates(ws, mid)
            return {
                'status': 'ok',
                'content': self._clean_text(body),
                'messages': messages,
                'raw_length': len(body),
            }

    async def _chat_async(self, prompt, timeout):
        async with websockets.connect(self._ws_url(ensure=True), max_size=10 * 1024 * 1024, open_timeout=10) as ws:
            mid = [0]
            selector = await self._wait_ready(ws, mid, timeout=30)
            if not selector:
                return {'status': 'error', 'error': 'input not found; login may be required'}

            before_body = str(await self._body_text(ws, mid))
            before_messages = await self._message_candidates(ws, mid)

            typed = await self._insert_prompt(ws, mid, prompt, selector)
            if str(typed) != 'OK':
                return {'status': 'error', 'error': f'type_failed:{typed}'}

            sent = await self._send_prompt(ws, mid, prompt, selector)
            if not sent.get('ok'):
                return {
                    'status': 'error',
                    'error': f'send_failed:{sent.get("method")}',
                    'composer': sent.get('composer', ''),
                }

            start = time.time()
            last_payload = ''
            stable = 0
            while time.time() - start < timeout:
                await asyncio.sleep(2)
                body = str(await self._body_text(ws, mid))
                messages = await self._message_candidates(ws, mid)
                payload = self._extract_response(messages, body, prompt)
                changed = (body != before_body) or (messages != before_messages)
                if changed and payload:
                    if payload == last_payload:
                        stable += 1
                        if stable >= 2:
                            return {
                                'status': 'ok',
                                'response': payload,
                                'elapsed': round(time.time() - start, 1),
                                'send_method': sent.get('method'),
                            }
                    else:
                        stable = 0
                        last_payload = payload

            body = str(await self._body_text(ws, mid))
            messages = await self._message_candidates(ws, mid)
            payload = self._extract_response(messages, body, prompt)
            return {
                'status': 'timeout',
                'response': payload,
                'elapsed': round(time.time() - start, 1),
                'send_method': sent.get('method'),
            }

    def health(self):
        try:
            version = self._http_json('/json/version', timeout=3)
            target = self._pick_target()
            return {
                'status': 'ok' if target else 'no_grok_tab',
                'browser': version.get('Browser'),
                'webSocketDebuggerUrl': bool(version.get('webSocketDebuggerUrl')),
                'target_url': target.get('url') if target else None,
                'version': VERSION,
            }
        except Exception as e:
            return {'status': 'cdp_down', 'error': str(e), 'version': VERSION}

    def new_chat(self):
        try:
            self._open_grok_tab()
            return {'status': 'ok', 'url': GROK_URL}
        except Exception as e:
            return {'status': 'error', 'error': str(e)}

    def history(self):
        try:
            return asyncio.run(self._history_async())
        except Exception as e:
            return {'status': 'error', 'error': str(e)}

    def chat(self, prompt, timeout=120):
        with self.lock:
            try:
                return asyncio.run(self._chat_async(prompt, timeout))
            except Exception as e:
                return {'status': 'error', 'error': str(e)}


bridge = None


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        raw = self.rfile.read(int(self.headers.get('Content-Length', 0)) or 0) or b'{}'
        data = json.loads(raw.decode())
        if self.path == '/chat':
            prompt = data.get('prompt', '')
            timeout = data.get('timeout', 120)
            ts = time.strftime('%H:%M:%S')
            print(f'[{ts}] >> {prompt[:120]}', flush=True)
            result = bridge.chat(prompt, timeout)
            print(f'[{ts}] << [{result.get("status")}] {str(result.get("response", result.get("error", "")))[:120]}', flush=True)
            return self._json(200, result)
        if self.path == '/new':
            return self._json(200, bridge.new_chat())
        self.send_response(404)
        self.end_headers()

    def do_GET(self):
        if self.path == '/health':
            return self._json(200, bridge.health())
        if self.path == '/history':
            return self._json(200, bridge.history())
        self.send_response(404)
        self.end_headers()

    def _json(self, code, data):
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode())

    def log_message(self, *_args):
        pass


class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=19998)
    parser.add_argument('--cdp-port', type=int, default=9222)
    args = parser.parse_args()

    bridge = GrokBridge(cdp_port=args.cdp_port)
    print(f'Grok Bridge {VERSION} {args.host}:{args.port} (CDP:{args.cdp_port})', flush=True)
    print('Prereq: Chrome started with --remote-debugging-port and logged into grok.com', flush=True)
    ThreadedHTTPServer((args.host, args.port), Handler).serve_forever()
