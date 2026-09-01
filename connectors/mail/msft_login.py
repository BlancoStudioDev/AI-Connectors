#!/usr/bin/env python3
"""One-time OAuth login (device flow) for a Microsoft/Outlook IMAP account.
Usage: msft_login.py  → prints link + code, waits for authorization, saves tokens.
"""
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
TOKENS = os.path.join(HERE, 'outlook_tokens.json')
CLIENT_ID = '9e5f94bc-e8a4-4e73-b8be-63364c29d753'  # well-known public Thunderbird client id
TENANT = 'common'
SCOPES = 'https://outlook.office.com/IMAP.AccessAsUser.All offline_access'
BASE = f'https://login.microsoftonline.com/{TENANT}/oauth2/v2.0'


def main():
    data = urllib.parse.urlencode({'client_id': CLIENT_ID, 'scope': SCOPES}).encode()
    r = urllib.request.urlopen(urllib.request.Request(f'{BASE}/devicecode', data=data), timeout=30)
    d = json.load(r)
    print(f"1) Open this link:  {d['verification_uri']}", flush=True)
    print(f"2) Enter the code:  {d['user_code']}", flush=True)
    print(f"3) Sign in with the account email and authorize. (expires in {d.get('expires_in', 900)}s)", flush=True)
    print("Waiting for authorization...", flush=True)
    interval = d.get('interval', 5)
    deadline = time.time() + d.get('expires_in', 900)
    while time.time() < deadline:
        time.sleep(interval)
        payload = urllib.parse.urlencode({
            'client_id': CLIENT_ID,
            'grant_type': 'urn:ietf:params:oauth:grant-type:device_code',
            'device_code': d['device_code'],
        }).encode()
        try:
            rr = urllib.request.urlopen(urllib.request.Request(f'{BASE}/token', data=payload), timeout=30)
            n = json.load(rr)
        except urllib.error.HTTPError as e:
            try:
                body = json.load(e)
            except Exception:
                continue
            err = body.get('error')
            if err == 'authorization_pending':
                continue
            if err == 'slow_down':
                interval += 5
                continue
            print(f"OAuth error: {err}: {body.get('error_description', '')[:200]}", flush=True)
            sys.exit(1)
        except Exception as e:
            print(f"Network: {e} — retrying", flush=True)
            continue
        json.dump({
            'access_token': n['access_token'],
            'refresh_token': n['refresh_token'],
            'expires_at': time.time() + int(n.get('expires_in', 3600)),
        }, open(TOKENS, 'w'))
        os.chmod(TOKENS, 0o600)
        print("✅ Login successful! Tokens saved. Now try: mail.py outlook", flush=True)
        return
    print("⌛ Timed out: run msft_login.py again", flush=True)
    sys.exit(2)


if __name__ == '__main__':
    main()
