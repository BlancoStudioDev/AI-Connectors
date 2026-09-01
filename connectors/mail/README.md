# 📬 Mail — read your mailboxes via IMAP

Reads and searches email across your IMAP accounts (Gmail, Outlook, school/work mailboxes) and summarizes them for the agent. Supports **password** accounts (app password) and **OAuth2** accounts (Microsoft, device flow).

## Files

- `mail.py` — the main script
- `msft_login.py` — one-time OAuth login for Microsoft/Outlook accounts (device flow, well-known public client ID)

## Dependencies

```bash
~/agent-scripts/.venv/bin/pip install imap-tools
```

## Configuration — `mail.env` (same style as .env, permission 600)

One block per account, with a free-form name (`gmail1`, `outlook`, ...):

```ini
# Password accounts (Gmail requires an "App password" with 2FA enabled)
MAIL_GMAIL1_HOST=imap.gmail.com
MAIL_GMAIL1_USER=you@gmail.com
MAIL_GMAIL1_PASS=abcd efgh ijkl mnop

# Microsoft/Outlook OAuth accounts (only HOST + USER needed; token comes from msft_login.py)
MAIL_OUTLOOK_HOST=outlook.office365.com
MAIL_OUTLOOK_USER=you@yourdomain.com
```

The account names in the `ACCOUNTS` list inside `mail.py` must match the suffixes used in the file. The account named `outlook` is special-cased for OAuth — rename freely if you keep the convention.

### One-time OAuth login (Microsoft accounts only)

```bash
~/agent-scripts/.venv/bin/python msft_login.py
# 1) open the link, 2) enter the code, 3) authorize
# → saves outlook_tokens.json (600), auto-refreshed afterwards
```

## Usage

```bash
mail.py                                # summary of all accounts (last 3)
mail.py gmail1 5                       # last 5 of account gmail1
mail.py all 10 --unread                # last 10 unread across all
mail.py gmail1 --search confirm        # search "confirm" in subject/text
mail.py gmail1 --search invoice --body # also show the body of the first hit
```

## Example output

```
📬 gmail1 (you@gmail.com) — Total: 1523 | Unread: 4
   🔵 [01/09 09:12] Amazon.com → Your package has been delivered
   🔵 [01/09 08:30] GitHub → [repo] New pull request
```
