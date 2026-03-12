#!/usr/bin/env python3
import argparse
import json
import sys
import urllib.error
import urllib.request


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--prompt', required=True)
    p.add_argument('--timeout', type=int, default=120)
    p.add_argument('--url', default='http://127.0.0.1:19998')
    p.add_argument('--json', action='store_true', dest='as_json')
    args = p.parse_args()

    req = urllib.request.Request(
        args.url.rstrip('/') + '/chat',
        data=json.dumps({'prompt': args.prompt, 'timeout': args.timeout}).encode(),
        headers={'Content-Type': 'application/json'},
        method='POST',
    )
    try:
        with urllib.request.urlopen(req, timeout=args.timeout + 30) as r:
            data = json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        sys.stderr.write(f'HTTPError: {e.code} {e.reason}\n')
        raise SystemExit(1)
    except Exception as e:
        sys.stderr.write(f'Request failed: {e}\n')
        raise SystemExit(1)

    if args.as_json:
        print(json.dumps(data, ensure_ascii=False))
        return

    status = data.get('status')
    if status in ('ok', 'timeout'):
        print(data.get('response', ''))
        return

    sys.stderr.write((data.get('error') or 'unknown grok bridge error') + '\n')
    raise SystemExit(1)


if __name__ == '__main__':
    main()
