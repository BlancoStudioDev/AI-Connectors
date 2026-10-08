# 📬 Mail — read via IMAP and send via Microsoft SMTP OAuth

Reads and searches email across your IMAP accounts (Gmail, Outlook, school/work mailboxes) and summarizes them for the agent. Supports **password** accounts (app password) and **OAuth2** accounts (Microsoft, device flow).

Sends plain-text email from the configured **Outlook/Microsoft 365** account using
SMTP with STARTTLS and OAuth2. Device login works on a server without a desktop:
complete the sign-in from a browser on another device.

## Files

- `mail.py` — the main script
- `msft_login.py` — one-time OAuth login for Microsoft/Outlook accounts (device flow, well-known public client ID)
- `mail_send.py` — Outlook SMTP submission, message preview and private receipts
- `msft_oauth.py` — shared token refresh and atomic private storage

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

To enable sending, request the additional delegated `SMTP.Send` permission:

```bash
~/agent-scripts/.venv/bin/python ~/agent-scripts/msft_login.py --with-send
```

The default login keeps requesting only IMAP and `offline_access`. Sending requires
`https://outlook.office.com/SMTP.Send` in addition to the IMAP scope; older token
files without scope metadata still work for reading, but require a new login with
`--with-send` before sending. IMAP and SMTP share `outlook_tokens.json`, and a
refresh triggered by reading preserves any SMTP grant. A local lock serializes
refresh-token rotation across processes. Tokens are replaced atomically with mode
`600` and are never included in command output.

The existing public client ID is unchanged. This does not override Microsoft
tenant policies: the organization must allow the OAuth consent and SMTP AUTH for
the mailbox. If consent requires administrator approval or SMTP authentication is
disabled, the command cannot send. See Microsoft's
[OAuth documentation for IMAP/POP/SMTP](https://learn.microsoft.com/en-us/exchange/client-developer/legacy-protocols/how-to-authenticate-an-imap-pop-smtp-application-by-using-oauth).

## Usage

```bash
mail.py                                # summary of all accounts (last 3)
mail.py gmail1 5                       # last 5 of account gmail1
mail.py all 10 --unread                # last 10 unread across all
mail.py gmail1 --search confirm        # search "confirm" in subject/text
mail.py gmail1 --search invoice --body # also show the body of the first hit
```

### Sending from Outlook

```bash
# Prepare a UTF-8 plain-text file, then preview without OAuth or SMTP access:
~/agent-scripts/.venv/bin/python ~/agent-scripts/mail_send.py outlook \
  --to recipient@example.org --subject 'Requested documents' \
  --body-file /path/to/message.txt --dry-run

# Send only when the user has requested or authorized this message:
~/agent-scripts/.venv/bin/python ~/agent-scripts/mail_send.py outlook \
  --to recipient@example.org --subject 'Requested documents' \
  --body-file /path/to/message.txt

# Alternatively pass the text directly; repeat --to for multiple recipients:
~/agent-scripts/.venv/bin/python ~/agent-scripts/mail_send.py outlook \
  --to recipient@example.org --to second@example.org \
  --subject 'Meeting follow-up' --body 'Thank you for the meeting.'
```

The sender is `MAIL_OUTLOOK_USER` from `mail.env`; there is no sender override.
Recipient addresses must be bare ASCII addresses. Unicode subjects and message
text are supported. This first version does not support Gmail sending,
attachments, HTML, CC or BCC. It requires only Python's standard library.

Submission uses `smtp.office365.com:587`, verifies the TLS certificate and
authenticates with SASL XOAUTH2 only after STARTTLS. Every recipient must be
accepted before the message is submitted with DATA; a rejected recipient aborts
the entire attempt. The connector never retries a submission automatically.

Each attempt stores a `.eml` message and a JSON receipt in
`data/mail-outbox/` (directory `700`, files `600`, git-ignored). Receipts contain
the Message-ID, recipients, subject and the SMTP response, but no OAuth tokens.
The final successful command prints the receipt as JSON:

- `prepared`: the message exists locally; DATA has not started.
- `submitting`: persisted immediately before DATA. If a process stops in this
  state, treat the result as uncertain.
- `accepted`: the server acknowledged DATA with SMTP `250`. This confirms
  submission, not delivery to the recipient.
- `failed`: authentication/envelope failed, or SMTP explicitly rejected DATA.
- `unknown`: connection loss, timeout or another unexpected failure during DATA.
  Check Sent mail and the Message-ID before any manual retry; the server may have
  accepted the message even though its acknowledgment was lost.

If storing the final receipt fails after SMTP acceptance, the command reports
`accepted` on stderr; the on-disk receipt may still say `submitting`. Verify the
message before retrying. The script does not append an IMAP Sent copy, avoiding
duplicates when the provider saves outgoing messages automatically.

### Tests

From the repository root, using Python 3.9 or newer:

```bash
python3 -m unittest discover -s tests -v
```

The tests simulate OAuth and SMTP, including scope preservation, verified TLS,
recipient rejection and lost acknowledgments. They do not send email or need
real credentials.

## Example output

```
📬 gmail1 (you@gmail.com) — Total: 1523 | Unread: 4
   🔵 [01/09 09:12] Amazon.com → Your package has been delivered
   🔵 [01/09 08:30] GitHub → [repo] New pull request
```
