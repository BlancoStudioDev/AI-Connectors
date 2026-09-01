#!/usr/bin/env python3
"""One-time Strava login: exchanges the authorization 'code' for tokens.
Usage: strava_login.py <code>
"""
import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
TOKENS = HERE / 'strava_tokens.json'


def load_cfg():
    cfg = {}
    env = HERE / '.env'
    if env.exists():
        for line in env.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                k, v = line.split('=', 1)
                cfg[k.strip()] = v.strip()
    return cfg


def main():
    if len(sys.argv) < 2:
        print("usage: strava_login.py <code>", file=sys.stderr)
        sys.exit(1)
    cfg = load_cfg()
    data = urllib.parse.urlencode({
        'client_id': cfg['STRAVA_CLIENT_ID'],
        'client_secret': cfg['STRAVA_CLIENT_SECRET'],
        'code': sys.argv[1],
        'grant_type': 'authorization_code',
    }).encode()
    req = urllib.request.Request('https://www.strava.com/oauth/token', data=data)
    with urllib.request.urlopen(req, timeout=30) as r:
        n = json.load(r)
    t = {'access_token': n['access_token'], 'refresh_token': n['refresh_token'], 'expires_at': n['expires_at']}
    json.dump(t, open(TOKENS, 'w'))
    os.chmod(TOKENS, 0o600)
    athlete = n.get('athlete', {})
    print(f"✅ Strava connected: {athlete.get('firstname', '')} {athlete.get('lastname', '')} — tokens saved. Try: strava.py stats")


if __name__ == '__main__':
    main()
