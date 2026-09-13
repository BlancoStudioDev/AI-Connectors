#!/usr/bin/env python3
"""Notifica Telegram: usa BOT_TOKEN di telegram-agent e il chat_id admin."""
import json, sys, urllib.parse, urllib.request
from pathlib import Path

TG = Path('/home/blanco05/telegram-agent')


def main():
    msg = ' '.join(sys.argv[1:]).strip()
    if not msg:
        return
    token = None
    for line in (TG / '.env').read_text().splitlines():
        if line.strip().startswith('BOT_TOKEN='):
            token = line.split('=', 1)[1].strip().strip('"')
    chat = json.load(open(TG / 'admin.json'))[0]
    data = urllib.parse.urlencode({'chat_id': chat, 'text': msg[:4000]}).encode()
    try:
        urllib.request.urlopen(urllib.request.Request(
            f'https://api.telegram.org/bot{token}/sendMessage', data=data), timeout=60)
    except Exception as e:
        print(f'notify error: {e}', file=sys.stderr)


if __name__ == '__main__':
    main()
