#!/usr/bin/env python3
"""Invia un video nella chat Telegram di Paloma (chat admin).
Uso: send_video.py <file.mp4> <caption>
"""
import json, sys, urllib.parse, urllib.request
from pathlib import Path

TG = Path('/home/blanco05/telegram-agent')
MAX = 50 * 1024 * 1024


def main():
    if len(sys.argv) < 2:
        print('uso: send_video.py <file> [caption]')
        return 1
    path = Path(sys.argv[1])
    caption = ' '.join(sys.argv[2:])[:1000] if len(sys.argv) > 2 else ''
    if not path.exists() or path.stat().st_size > MAX:
        print(f'file non valido o troppo grande: {path}')
        return 1
    token = None
    for line in (TG / '.env').read_text().splitlines():
        if line.strip().startswith('BOT_TOKEN='):
            token = line.split('=', 1)[1].strip().strip('"')
    chat = json.load(open(TG / 'admin.json'))[0]
    data = urllib.parse.urlencode({
        'chat_id': chat, 'caption': caption, 'supports_streaming': 'true',
    }).encode()
    boundary = '----blancoShorts'
    body = b''
    for k, v in [('chat_id', chat), ('caption', caption), ('supports_streaming', 'true')]:
        body += f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode()
    body += (f'--{boundary}\r\nContent-Disposition: form-data; name="video"; '
             f'filename="{path.name}"\r\nContent-Type: video/mp4\r\n\r\n').encode()
    body += path.read_bytes() + f'\r\n--{boundary}--\r\n'.encode()
    req = urllib.request.Request(
        f'https://api.telegram.org/bot{token}/sendVideo', data=body,
        headers={'Content-Type': f'multipart/form-data; boundary={boundary}'})
    try:
        r = json.load(urllib.request.urlopen(req, timeout=300))
        if r.get('ok'):
            print('VIDEO INVIATO')
            return 0
        print('errore telegram: ' + json.dumps(r)[:200])
        return 1
    except Exception as e:
        print('invio fallito: ' + str(e)[:200])
        return 1


if __name__ == '__main__':
    sys.exit(main())
