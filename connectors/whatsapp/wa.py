#!/usr/bin/env python3
"""FAST WhatsApp skill (queries the local bridge API, default 127.0.0.1:3789).
Usage:
  wa.py read [--hours N] [--minutes N] [--chat NAME] [--search TEXT] [--limit N]
  wa.py chats
  wa.py send CHAT "text"
  wa.py status

The bridge (a small Baileys/Node service running your own WhatsApp session)
must expose: /status, /chats, /messages?hours=&minutes=&chat=&search=&limit=,
/send?chat=&text= — see README.md. Override the URL with WA_API_URL in .env.
"""
import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ENVF = Path(__file__).resolve().parent / ".env"
WA_API_URL = 'http://127.0.0.1:3789'
if ENVF.exists():
    for line in ENVF.read_text().splitlines():
        if line.strip().startswith('WA_API_URL='):
            WA_API_URL = line.split('=', 1)[1].strip()

TZ = ZoneInfo(os.environ.get('WA_TZ', 'Europe/Rome'))


def get(path):
    with urllib.request.urlopen(WA_API_URL + path, timeout=15) as r:
        return json.load(r)


def loc(t):
    try:
        return datetime.fromisoformat(t.replace('Z', '+00:00')).astimezone(TZ).strftime('%d/%m %H:%M')
    except Exception:
        return t[:16]


def main():
    args = list(sys.argv[1:])
    cmd = args.pop(0) if args else 'read'
    opts = {}
    key = None
    for a in args:
        if a.startswith('--'):
            key = a[2:]
            opts[key] = None
        elif key:
            opts[key] = a
            key = None

    if cmd == 'status':
        s = get('/status')
        print(f"{'✅ connected' if s.get('connected') else '❌ disconnected'} | messages in memory: {s.get('messages')}")
        return
    if cmd == 'send':
        rest = [a for a in args if not a.startswith('--')]
        if len(rest) < 2:
            print('usage: wa.py send CHAT "text"  (CHAT = exact name, jid or phone number)')
            sys.exit(1)
        r = get('/send?' + urllib.parse.urlencode({'chat': rest[0], 'text': ' '.join(rest[1:])}))
        print('✅ Sent on WhatsApp' if r.get('ok') else '❌ ' + r.get('error', 'error'))
        return
    if cmd == 'chats':
        for c in get('/chats'):
            print(f"{(c['name'] or '?')[:36]:36} | {c['count']:4} msgs | last: {loc(c['last'])} ({(c['lastSender'] or '?')[:18]})")
        return
    if cmd != 'read':
        print('usage: wa.py read [--hours N] [--minutes N] [--chat NAME] [--search TEXT] [--limit N] | chats | send CHAT "text" | status')
        sys.exit(1)

    params = {}
    if opts.get('hours'):
        params['hours'] = opts['hours']
    if opts.get('minutes'):
        params['minutes'] = opts['minutes']
    if opts.get('chat'):
        params['chat'] = opts['chat']
    if opts.get('search'):
        params['search'] = opts['search']
    if opts.get('limit'):
        params['limit'] = opts['limit']
    if not params:
        params['hours'] = '2'
    msgs = get('/messages?' + urllib.parse.urlencode(params))
    print(f"📱 WhatsApp — {len(msgs)} messages")
    for m in msgs:
        who = m.get('name') or '?'
        txt = (m.get('text') or '').replace('\n', ' ')[:140]
        print(f"  [{loc(m['t'])}] {(m.get('chatName') or '?')[:26]} · {who[:18]}: {txt}")


if __name__ == '__main__':
    main()
