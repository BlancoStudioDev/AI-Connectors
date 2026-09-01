#!/usr/bin/env python3
"""Email skill: read your mailboxes via IMAP.
Usage:
  mail.py                                  # summary of all accounts (last 3)
  mail.py outlook 5                        # last 5 of account 'outlook'
  mail.py all 10 --unread                  # last 10 unread across all
  mail.py gmail1 --search confirm          # search for 'confirm' (subject/body)
  mail.py gmail1 --search invoice --body   # also show the body of the first hit
Accounts: outlook (OAuth), gmail1, gmail2, gmail3 (or 'all') — see ACCOUNTS below.
"""
import base64
import json
import os
import socket
import sys
import time
import urllib.parse
import urllib.request

socket.setdefaulttimeout(25)

try:
    from imap_tools import AND, MailBox
except ImportError:
    print("ERROR: missing imap-tools (pip install imap-tools)")
    sys.exit(1)

HERE = os.path.dirname(os.path.abspath(__file__))
CFG = {}
for line in open(os.path.join(HERE, 'mail.env')):
    line = line.strip()
    if line and not line.startswith('#') and '=' in line:
        k, v = line.split('=', 1)
        CFG[k] = v

ACCOUNTS = ['outlook', 'gmail1', 'gmail2', 'gmail3']

TOKENS = os.path.join(HERE, 'outlook_tokens.json')
CLIENT_ID = '9e5f94bc-e8a4-4e73-b8be-63364c29d753'  # well-known public Thunderbird client id
TENANT = 'common'
SCOPES = 'https://outlook.office.com/IMAP.AccessAsUser.All offline_access'


def get_outlook_token():
    try:
        t = json.load(open(TOKENS))
    except Exception:
        return None
    if t.get('expires_at', 0) - 120 < time.time():
        try:
            data = urllib.parse.urlencode({
                'client_id': CLIENT_ID,
                'grant_type': 'refresh_token',
                'refresh_token': t['refresh_token'],
                'scope': SCOPES,
            }).encode()
            r = urllib.request.urlopen(urllib.request.Request(
                f'https://login.microsoftonline.com/{TENANT}/oauth2/v2.0/token', data=data), timeout=30)
            n = json.load(r)
            t['access_token'] = n['access_token']
            t['refresh_token'] = n.get('refresh_token', t['refresh_token'])
            t['expires_at'] = time.time() + int(n.get('expires_in', 3600))
            json.dump(t, open(TOKENS, 'w'))
            os.chmod(TOKENS, 0o600)
        except Exception:
            return None
    return t.get('access_token')


def cfg(name):
    h = CFG.get(f'MAIL_{name.upper()}_HOST')
    u = CFG.get(f'MAIL_{name.upper()}_USER')
    p = CFG.get(f'MAIL_{name.upper()}_PASS')
    if not (h and u):
        return None
    return h, u, p


def fmt_msg(m):
    when = m.date.strftime('%d/%m %H:%M') if m.date else '?'
    frm = (m.from_ or '?').replace('\n', ' ')[:52]
    subj = (m.subject or '(no subject)').replace('\n', ' ')[:80]
    seen = '  ' if m.flags and '\\Seen' in m.flags else '🔵'
    return f"{seen} [{when}] {frm} → {subj}"


def check(name, limit=3, only_unread=False, query=None, with_body=False):
    c = cfg(name)
    if not c:
        return f"⚠️ {name}: missing configuration"
    host, user, p = c
    try:
        with MailBox(host) as mb:
            if name == 'outlook':
                tok = get_outlook_token()
                if not tok:
                    return (f"❌ {name}: OAuth token missing or expired.\n"
                            f"   Login again: the agent must run ~/agent-scripts/msft_login.py")
                mb.xoauth2(user, tok)
            else:
                mb.login(user, p, initial_folder='INBOX')
            total = len(mb.numbers('ALL'))
            unread = len(mb.numbers('UNSEEN'))
            if only_unread:
                crit = 'UNSEEN'
            elif query:
                crit = AND(text=query)
            else:
                crit = None
            if crit is None:
                msgs = list(mb.fetch(limit=limit, reverse=True, mark_seen=False))
            else:
                msgs = list(mb.fetch(crit, limit=limit, reverse=True, mark_seen=False))
            out = [f"📬 {name} ({user}) — Total: {total} | Unread: {unread}"]
            if not msgs:
                out.append("   (no emails)" if not only_unread else "   (all read ✓)")
            for m in msgs:
                out.append("   " + fmt_msg(m))
                if with_body and m is msgs[0]:
                    body = (m.text or (m.html and '[HTML]') or '(empty)').strip()[:700]
                    out.append("   ── body ──\n   " + body.replace('\n', '\n   ')[:700])
            return '\n'.join(out)
    except Exception as e:
        msg = str(e).splitlines()[0][:120] if str(e) else e.__class__.__name__
        hint = ""
        es = str(e).upper()
        if 'AUTHENTICATE' in es or 'LOGIN' in es or 'CREDENTIALS' in es:
            hint = " → credentials rejected: for Gmail you need an 'app password' (with 2FA enabled)"
        return f"❌ {name}: {msg}{hint}"


def main():
    args = ' '.join(sys.argv[1:]).split()
    account, limit, only_unread, query, with_body = 'all', 3, False, None, False
    i = 0
    while i < len(args):
        a = args[i]
        if a in ('--search',):
            i += 1
            query = args[i] if i < len(args) else None
        elif a == '--unread':
            only_unread = True
        elif a == '--body':
            with_body = True
        elif a.isdigit():
            limit = int(a)
        elif a in ACCOUNTS + ['all']:
            account = a
        i += 1
    names = ACCOUNTS if account == 'all' else [account]
    print('\n\n'.join(check(n, limit, only_unread, query, with_body) for n in names))


if __name__ == '__main__':
    main()
