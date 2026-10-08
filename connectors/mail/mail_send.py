#!/usr/bin/env python3
"""Send plain-text email from the configured Outlook account over SMTP OAuth."""
import argparse
from contextlib import contextmanager
from email.message import EmailMessage
from email.policy import SMTP
from email.utils import formatdate, make_msgid
import json
import os
from pathlib import Path
import re
import smtplib
import ssl
import sys
import uuid

from msft_oauth import get_outlook_token, save_json

HERE = Path(__file__).resolve().parent
OUTBOX = HERE / 'data' / 'mail-outbox'
SMTP_HOST = 'smtp.office365.com'


def outlook_user():
    with (HERE / 'mail.env').open(encoding='utf-8') as file:
        for line in file:
            key, separator, value = line.strip().partition('=')
            if separator and key == 'MAIL_OUTLOOK_USER':
                return value.strip()
    raise ValueError('Missing MAIL_OUTLOOK_USER in mail.env.')


def build_message(sender, recipients, subject, body):
    if not recipients or not subject.strip() or not body.strip():
        raise ValueError('Recipients, subject and body must not be empty.')
    for address in [sender, *recipients]:
        if not address.isascii() or not re.fullmatch(
                r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+", address):
            raise ValueError('Use bare ASCII email addresses, without display names.')
    message = EmailMessage()
    message['From'] = sender
    message['To'] = ', '.join(recipients)
    message['Subject'] = subject
    message['Date'] = formatdate(localtime=False)
    message['Message-ID'] = make_msgid(domain=sender.rsplit('@', 1)[1])
    message.set_content(body, cte='quoted-printable')
    return message


@contextmanager
def smtp_session(sender, token):
    server = smtplib.SMTP(SMTP_HOST, 587, timeout=30)
    try:
        server.ehlo()
        server.starttls(context=ssl.create_default_context())
        server.ehlo()
        sent = False

        def authenticate(_challenge=None):
            nonlocal sent
            if sent:
                return ''
            sent = True
            return f'user={sender}\x01auth=Bearer {token}\x01\x01'

        server.auth('XOAUTH2', authenticate)
        yield server
    finally:
        try:
            server.quit()
        except (smtplib.SMTPException, OSError):
            server.close()


def send_message(sender, recipients, subject, body):
    message = build_message(sender, recipients, subject, body)
    payload = message.as_bytes(policy=SMTP)
    token = get_outlook_token(require_send=True)
    OUTBOX.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(OUTBOX, 0o700)
    request_id = uuid.uuid4().hex
    message_path = OUTBOX / f'{request_id}.eml'
    receipt_path = OUTBOX / f'{request_id}.json'
    with os.fdopen(os.open(message_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'wb') as file:
        file.write(payload)
        file.flush()
        os.fsync(file.fileno())
    receipt = {
        'status': 'prepared', 'from': sender, 'to': recipients,
        'subject': subject, 'message_id': str(message['Message-ID']),
        'message_file': str(message_path), 'receipt_file': str(receipt_path),
    }
    save_json(receipt_path, receipt)
    try:
        with smtp_session(sender, token) as server:
            code, response = server.mail(sender)
            if code != 250:
                raise smtplib.SMTPSenderRefused(code, response, sender)
            for recipient in recipients:
                code, response = server.rcpt(recipient)
                if code not in (250, 251, 252):
                    raise smtplib.SMTPRecipientsRefused({recipient: (code, response)})
            # Persist uncertainty before DATA: a lost connection or process crash
            # after submission must never trigger an automatic retry.
            receipt['status'] = 'submitting'
            save_json(receipt_path, receipt)
            code, response = server.data(payload)
            if code != 250:
                raise smtplib.SMTPDataError(code, response)
            receipt.update(status='accepted', smtp_code=code,
                           smtp_response=response.decode('utf-8', errors='replace'),
                           accepted_at=formatdate(localtime=False))
            save_json(receipt_path, receipt)
    except Exception as error:
        if receipt['status'] != 'accepted':
            uncertain = (receipt['status'] == 'submitting' and
                         not isinstance(error, smtplib.SMTPResponseException))
            receipt['status'] = 'unknown' if uncertain else 'failed'
            # Store only an error type: server exceptions may contain sensitive text.
            receipt['error'] = type(error).__name__
            save_json(receipt_path, receipt)
        print(f"SMTP status: {receipt['status']}. Receipt: {receipt_path}", file=sys.stderr)
        if receipt['status'] in ('submitting', 'unknown', 'accepted'):
            print('Check this Message-ID in Sent mail before any manual retry.', file=sys.stderr)
        raise
    return receipt


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('account', choices=['outlook'])
    parser.add_argument('--to', action='append', required=True,
                        help='Bare recipient address; repeat for multiple recipients.')
    parser.add_argument('--subject', required=True)
    body = parser.add_mutually_exclusive_group(required=True)
    body.add_argument('--body', help='Plain-text message.')
    body.add_argument('--body-file', type=Path, help='UTF-8 plain-text message file.')
    parser.add_argument('--dry-run', action='store_true',
                        help='Show the MIME message without accessing OAuth or SMTP.')
    args = parser.parse_args(argv)
    try:
        sender = outlook_user()
        text = args.body_file.read_text(encoding='utf-8') if args.body_file else args.body
        if args.dry_run:
            print(build_message(sender, args.to, args.subject, text).as_string(policy=SMTP))
            return 0
        result = send_message(sender, args.to, args.subject, text)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except RuntimeError as error:
        # Token helper errors are local, contain no credentials and give login hints.
        print(f'ERROR: {error}', file=sys.stderr)
    except (OSError, ValueError, smtplib.SMTPException) as error:
        print(f'ERROR: {type(error).__name__}. Check configuration, SMTP AUTH and the receipt.',
              file=sys.stderr)
    return 1


if __name__ == '__main__':
    sys.exit(main())
