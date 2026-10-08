#!/usr/bin/env python3
"""One-time OAuth login (device flow) for a Microsoft/Outlook account.
Usage: msft_login.py [--with-send] → authorize IMAP, optionally SMTP, and save tokens.
"""
import argparse
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

from msft_oauth import BASE, CLIENT_ID, SCOPES, SEND_SCOPES, TOKENS, save_json, token_lock, token_record


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--with-send', action='store_true', help='Request SMTP.Send as well as IMAP access.')
    args = parser.parse_args(argv)
    scopes = SEND_SCOPES if args.with_send else SCOPES
    data = urllib.parse.urlencode({'client_id': CLIENT_ID, 'scope': scopes}).encode()
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
        with token_lock():
            save_json(TOKENS, token_record(n, requested_scopes=scopes))
        print("✅ Login successful! Tokens saved. Now try: mail.py outlook", flush=True)
        return
    print("⌛ Timed out: run msft_login.py again", flush=True)
    sys.exit(2)


if __name__ == '__main__':
    main()
