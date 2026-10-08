"""Shared Microsoft token storage and refresh for IMAP and SMTP (stdlib only)."""
from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import tempfile
import time
import urllib.parse
import urllib.request

HERE = Path(__file__).resolve().parent
TOKENS = HERE / 'outlook_tokens.json'
CLIENT_ID = '9e5f94bc-e8a4-4e73-b8be-63364c29d753'  # existing public Thunderbird client id
TENANT = 'common'
BASE = f'https://login.microsoftonline.com/{TENANT}/oauth2/v2.0'
IMAP_SCOPE = 'https://outlook.office.com/IMAP.AccessAsUser.All'
SMTP_SCOPE = 'https://outlook.office.com/SMTP.Send'
SCOPES = f'{IMAP_SCOPE} offline_access'
SEND_SCOPES = f'{IMAP_SCOPE} {SMTP_SCOPE} offline_access'


def save_json(path, record):
    """Replace a private JSON file atomically; never leave a partially written token."""
    path = Path(path)
    fd, temporary = tempfile.mkstemp(prefix=f'.{path.name}.', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as file:
            json.dump(record, file, ensure_ascii=False)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


@contextmanager
def token_lock():
    """Serialize refresh-token rotation across reading and sending processes."""
    lock_path = TOKENS.with_suffix('.lock')
    fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
    with os.fdopen(fd, 'a') as lock:
        deadline = time.monotonic() + 35
        while True:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise RuntimeError('Microsoft token is busy; try again later.')
                time.sleep(0.1)
        try:
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def token_record(response, previous=None, requested_scopes=SCOPES):
    previous = previous or {}
    return {
        'access_token': response['access_token'],
        'refresh_token': response.get('refresh_token', previous.get('refresh_token')),
        'expires_at': time.time() + int(response.get('expires_in', 3600)),
        'scope': response.get('scope', previous.get('scope', requested_scopes)),
    }


def get_outlook_token(require_send=False):
    """Return the access token, preserving SMTP grants when IMAP renews it."""
    with token_lock():
        try:
            with TOKENS.open(encoding='utf-8') as file:
                record = json.load(file)
        except (OSError, ValueError):
            raise RuntimeError('OAuth token missing; run msft_login.py' +
                               (' --with-send.' if require_send else '.')) from None
        scopes = record.get('scope', SCOPES).split()
        if require_send and SMTP_SCOPE not in scopes:
            raise RuntimeError('SMTP.Send permission missing; run msft_login.py --with-send.')
        if record.get('expires_at', 0) - 120 < time.time():
            requested = SEND_SCOPES if SMTP_SCOPE in scopes else SCOPES
            if not record.get('refresh_token'):
                raise RuntimeError('OAuth refresh token missing; run msft_login.py' +
                                   (' --with-send.' if SMTP_SCOPE in scopes else '.'))
            payload = urllib.parse.urlencode({
                'client_id': CLIENT_ID,
                'grant_type': 'refresh_token',
                'refresh_token': record['refresh_token'],
                'scope': requested,
            }).encode()
            try:
                with urllib.request.urlopen(urllib.request.Request(
                        f'{BASE}/token', data=payload), timeout=30) as response:
                    renewed = token_record(json.load(response), record, requested)
            except (OSError, ValueError, KeyError):
                raise RuntimeError('OAuth refresh failed; run msft_login.py' +
                                   (' --with-send.' if SMTP_SCOPE in scopes else '.')) from None
            save_json(TOKENS, renewed)
            record = renewed
        if require_send and SMTP_SCOPE not in record.get('scope', '').split():
            raise RuntimeError('SMTP.Send permission missing; run msft_login.py --with-send.')
        if not record.get('access_token'):
            raise RuntimeError('OAuth access token missing; run msft_login.py again.')
        return record['access_token']
