"""No-network tests for Microsoft SMTP submission and shared OAuth refresh."""
import contextlib
import io
import json
from pathlib import Path
import shutil
import smtplib
import ssl
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import MagicMock, patch
import urllib.parse

MAIL_DIR = Path(__file__).resolve().parents[1] / 'connectors' / 'mail'
sys.path.insert(0, str(MAIL_DIR))
import mail_send
import msft_login
import msft_oauth as oauth


class TokenTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.tokens = Path(self.directory.name) / 'outlook_tokens.json'
        self.patcher = patch.object(oauth, 'TOKENS', self.tokens)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

    def record(self, scope=oauth.SCOPES, expired=False):
        return {'access_token': 'test-access', 'refresh_token': 'test-refresh',
                'scope': scope, 'expires_at': 0 if expired else time.time() + 3600}

    def test_existing_imap_only_tokens_still_work_for_reading(self):
        legacy = self.record()
        del legacy['scope']
        oauth.save_json(self.tokens, legacy)
        with patch.object(oauth.urllib.request, 'urlopen') as request:
            self.assertEqual(oauth.get_outlook_token(), 'test-access')
        request.assert_not_called()

    def test_missing_smtp_scope_does_not_attempt_refresh_or_smtp(self):
        oauth.save_json(self.tokens, self.record(expired=True))
        with patch.object(oauth.urllib.request, 'urlopen') as request:
            with self.assertRaisesRegex(RuntimeError, 'msft_login.py --with-send'):
                oauth.get_outlook_token(require_send=True)
        request.assert_not_called()

    def test_read_refresh_preserves_smtp_permission_and_rotated_refresh_token(self):
        oauth.save_json(self.tokens, self.record(oauth.SEND_SCOPES, expired=True))
        response = io.BytesIO(json.dumps({'access_token': 'renewed',
                                         'refresh_token': 'rotated',
                                         'expires_in': 3600,
                                         'scope': oauth.SEND_SCOPES}).encode())
        with patch.object(oauth.urllib.request, 'urlopen', return_value=response) as request:
            self.assertEqual(oauth.get_outlook_token(), 'renewed')
        form = urllib.parse.parse_qs(request.call_args.args[0].data.decode())
        self.assertEqual(form['scope'], [oauth.SEND_SCOPES])
        self.assertEqual(form['refresh_token'], ['test-refresh'])
        saved = json.loads(self.tokens.read_text())
        self.assertEqual(saved['refresh_token'], 'rotated')
        self.assertIn(oauth.SMTP_SCOPE, saved['scope'].split())
        self.assertEqual(self.tokens.stat().st_mode & 0o777, 0o600)

    def test_refresh_without_rotation_retains_previous_refresh_token(self):
        oauth.save_json(self.tokens, self.record(oauth.SEND_SCOPES, expired=True))
        response = io.BytesIO(b'{"access_token": "renewed", "expires_in": 3600}')
        with patch.object(oauth.urllib.request, 'urlopen', return_value=response):
            self.assertEqual(oauth.get_outlook_token(require_send=True), 'renewed')
        self.assertEqual(json.loads(self.tokens.read_text())['refresh_token'], 'test-refresh')

    def test_refresh_failure_preserves_previous_file_and_hides_credentials(self):
        original = self.record(oauth.SEND_SCOPES, expired=True)
        oauth.save_json(self.tokens, original)
        with patch.object(oauth.urllib.request, 'urlopen', side_effect=OSError('test-refresh')):
            with self.assertRaisesRegex(RuntimeError, 'OAuth refresh failed') as error:
                oauth.get_outlook_token(require_send=True)
        self.assertNotIn('test-refresh', str(error.exception))
        self.assertEqual(json.loads(self.tokens.read_text()), original)

    def test_missing_refresh_token_gives_a_login_hint(self):
        record = self.record(oauth.SEND_SCOPES, expired=True)
        del record['refresh_token']
        oauth.save_json(self.tokens, record)
        with self.assertRaisesRegex(RuntimeError, 'msft_login.py --with-send'):
            oauth.get_outlook_token(require_send=True)

    def test_atomic_write_failure_keeps_previous_record_and_removes_temporary_file(self):
        oauth.save_json(self.tokens, self.record())
        before = self.tokens.read_bytes()
        with patch.object(oauth.os, 'replace', side_effect=OSError('disk error')):
            with self.assertRaises(OSError):
                oauth.save_json(self.tokens, {'access_token': 'replacement'})
        self.assertEqual(self.tokens.read_bytes(), before)
        self.assertEqual(list(self.tokens.parent.glob('.outlook_tokens.json.*')), [])

    def test_login_requests_smtp_only_when_opted_in(self):
        for args, expected in [([], oauth.SCOPES), (['--with-send'], oauth.SEND_SCOPES)]:
            device = io.StringIO(json.dumps({'verification_uri': 'https://example.invalid/device',
                                             'user_code': 'TEST', 'device_code': 'device',
                                             'interval': 1, 'expires_in': 900}))
            grant = io.StringIO(json.dumps({'access_token': 'test-access',
                                            'refresh_token': 'test-refresh', 'scope': expected}))
            with patch.object(msft_login.urllib.request, 'urlopen', side_effect=[device, grant]) as request, \
                    patch.object(msft_login.time, 'sleep'), \
                    patch.object(msft_login, 'TOKENS', self.tokens), \
                    contextlib.redirect_stdout(io.StringIO()):
                msft_login.main(args)
            form = urllib.parse.parse_qs(request.call_args_list[0].args[0].data.decode())
            self.assertEqual(form['scope'], [expected])
            self.assertEqual(json.loads(self.tokens.read_text())['scope'], expected)


class SendingTests(unittest.TestCase):
    sender = 'sender@example.org'
    recipients = ['recipient@example.org', 'second@example.org']

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.outbox = Path(self.directory.name) / 'outbox'
        self.patcher = patch.object(mail_send, 'OUTBOX', self.outbox)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

    def test_mime_preserves_unicode_subject_body_and_uses_configured_sender(self):
        message = mail_send.build_message(self.sender, self.recipients, 'Università', 'Crediti già acquisiti')
        self.assertEqual(message['From'], self.sender)
        self.assertEqual(message['To'], ', '.join(self.recipients))
        self.assertEqual(str(message['Subject']), 'Università')
        self.assertEqual(message.get_content().strip(), 'Crediti già acquisiti')
        self.assertTrue(message['Message-ID'])
        # Seven-bit transfer encoding works without requiring SMTPUTF8/8BITMIME.
        message.as_bytes(policy=mail_send.SMTP).decode('ascii')

    def test_header_injection_and_non_bare_addresses_are_rejected(self):
        for address in ['a@example.org\r\nBcc: b@example.org', 'Name <a@example.org>',
                        'a@example.org(comment)', 'a@example.org\x01', 'ä@example.org']:
            with self.subTest(address=address), self.assertRaises(ValueError):
                mail_send.build_message(self.sender, [address], 'Subject', 'Body')
        with self.assertRaises(ValueError):
            mail_send.build_message(self.sender, self.recipients, 'Subject\nBcc: b@example.org', 'Body')

    def test_empty_fields_do_not_access_tokens(self):
        with patch.object(mail_send, 'get_outlook_token') as token:
            for recipients, subject, body in [([], 'Subject', 'Body'), (self.recipients, ' ', 'Body'),
                                               (self.recipients, 'Subject', '')]:
                with self.assertRaises(ValueError):
                    mail_send.send_message(self.sender, recipients, subject, body)
        token.assert_not_called()

    def test_tls_precedes_authentication_and_challenge_does_not_repeat_token(self):
        server = MagicMock()
        with patch.object(mail_send.smtplib, 'SMTP', return_value=server) as factory:
            with mail_send.smtp_session(self.sender, 'test-token'):
                pass
        factory.assert_called_once_with('smtp.office365.com', 587, timeout=30)
        self.assertEqual([call[0] for call in server.mock_calls][:4], ['ehlo', 'starttls', 'ehlo', 'auth'])
        context = server.starttls.call_args.kwargs['context']
        self.assertTrue(context.check_hostname)
        self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
        mechanism, callback = server.auth.call_args.args
        self.assertEqual(mechanism, 'XOAUTH2')
        self.assertEqual(callback(), f'user={self.sender}\x01auth=Bearer test-token\x01\x01')
        self.assertEqual(callback(b'challenge'), '')

    def test_tls_failure_never_authenticates(self):
        server = MagicMock()
        server.starttls.side_effect = ssl.SSLError('verification failed')
        with patch.object(mail_send.smtplib, 'SMTP', return_value=server):
            with self.assertRaises(ssl.SSLError):
                with mail_send.smtp_session(self.sender, 'test-token'):
                    pass
        server.auth.assert_not_called()

    def send(self, rcpt=None, data=None, sender_code=250):
        server = MagicMock()
        server.mail.return_value = (sender_code, b'Envelope response')
        server.rcpt.side_effect = rcpt or [(250, b'OK'), (250, b'OK')]
        if isinstance(data, Exception):
            server.data.side_effect = data
        else:
            server.data.return_value = data or (250, b'Queued')
        @contextlib.contextmanager
        def session(_sender, _token):
            yield server
        error = None
        with patch.object(mail_send, 'get_outlook_token', return_value='test-token') as token, \
                patch.object(mail_send, 'smtp_session', session), \
                contextlib.redirect_stderr(io.StringIO()):
            try:
                mail_send.send_message(self.sender, self.recipients, 'Subject', 'Body')
            except Exception as caught:
                error = caught
        token.assert_called_once_with(require_send=True)
        receipt_path = next(self.outbox.glob('*.json'))
        receipt = json.loads(receipt_path.read_text())
        self.assertNotIn('test-token', receipt_path.read_text())
        return receipt, error, server

    def test_acceptance_is_recorded_only_after_250_and_data_is_called_once(self):
        receipt, error, server = self.send()
        self.assertIsNone(error)
        self.assertEqual(receipt['status'], 'accepted')
        self.assertEqual(receipt['smtp_code'], 250)
        server.data.assert_called_once()
        server.mail.assert_called_once_with(self.sender)
        self.assertEqual(server.rcpt.call_count, 2)
        self.assertEqual(self.outbox.stat().st_mode & 0o777, 0o700)
        for path in self.outbox.iterdir():
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertIn(receipt['message_id'].encode(), Path(receipt['message_file']).read_bytes())

    def test_any_recipient_rejection_aborts_before_data(self):
        receipt, error, server = self.send(rcpt=[(250, b'OK'), (550, b'Rejected')])
        self.assertIsInstance(error, smtplib.SMTPRecipientsRefused)
        self.assertEqual(receipt['status'], 'failed')
        server.data.assert_not_called()

    def test_sender_rejection_aborts_before_recipients(self):
        receipt, error, server = self.send(sender_code=550)
        self.assertIsInstance(error, smtplib.SMTPSenderRefused)
        self.assertEqual(receipt['status'], 'failed')
        server.rcpt.assert_not_called()
        server.data.assert_not_called()

    def test_disconnect_during_data_is_unknown_and_never_retried(self):
        receipt, error, server = self.send(data=smtplib.SMTPServerDisconnected('lost connection'))
        self.assertIsNotNone(error)
        self.assertEqual(receipt['status'], 'unknown')
        server.data.assert_called_once()

    def test_timeout_during_data_is_unknown_and_never_retried(self):
        receipt, error, server = self.send(data=TimeoutError('timeout'))
        self.assertIsNotNone(error)
        self.assertEqual(receipt['status'], 'unknown')
        server.data.assert_called_once()

    def test_explicit_data_rejection_is_failed(self):
        for response in [(550, b'Rejected'), smtplib.SMTPDataError(554, b'Rejected')]:
            with self.subTest(response=response):
                # Separate receipts for each send attempt.
                for path in self.outbox.glob('*'):
                    path.unlink()
                receipt, error, server = self.send(data=response)
                self.assertIsInstance(error, smtplib.SMTPDataError)
                self.assertEqual(receipt['status'], 'failed')
                server.data.assert_called_once()

    def test_missing_permission_never_opens_smtp_or_creates_outbox(self):
        with patch.object(mail_send, 'get_outlook_token', side_effect=RuntimeError('SMTP.Send missing')), \
                patch.object(mail_send, 'smtp_session') as session:
            with self.assertRaises(RuntimeError):
                mail_send.send_message(self.sender, self.recipients, 'Subject', 'Body')
        session.assert_not_called()
        self.assertFalse(self.outbox.exists())

    def test_quit_failure_does_not_undo_acceptance(self):
        server = MagicMock()
        server.mail.return_value = (250, b'OK')
        server.rcpt.return_value = (250, b'OK')
        server.data.return_value = (250, b'Queued')
        server.quit.side_effect = smtplib.SMTPServerDisconnected('lost on QUIT')
        with patch.object(mail_send, 'get_outlook_token', return_value='test-token'), \
                patch.object(mail_send.smtplib, 'SMTP', return_value=server):
            receipt = mail_send.send_message(self.sender, self.recipients, 'Subject', 'Body')
        self.assertEqual(receipt['status'], 'accepted')
        server.data.assert_called_once()
        server.close.assert_called_once()

    def test_receipt_storage_failure_after_acceptance_reports_accepted_without_resending(self):
        server = MagicMock()
        server.mail.return_value = (250, b'OK')
        server.rcpt.return_value = (250, b'OK')
        server.data.return_value = (250, b'Queued')
        writes = 0
        def failing_save(path, record):
            nonlocal writes
            writes += 1
            if writes == 3:
                raise OSError('disk full after acceptance')
            oauth.save_json(path, record)
        stderr = io.StringIO()
        with patch.object(mail_send, 'get_outlook_token', return_value='test-token'), \
                patch.object(mail_send.smtplib, 'SMTP', return_value=server), \
                patch.object(mail_send, 'save_json', side_effect=failing_save), \
                contextlib.redirect_stderr(stderr):
            with self.assertRaises(OSError):
                mail_send.send_message(self.sender, self.recipients, 'Subject', 'Body')
        self.assertIn('SMTP status: accepted', stderr.getvalue())
        self.assertEqual(json.loads(next(self.outbox.glob('*.json')).read_text())['status'], 'submitting')
        server.data.assert_called_once()

    def test_cli_dry_run_with_utf8_body_file_needs_no_tokens(self):
        root = Path(self.directory.name)
        for filename in ['mail_send.py', 'msft_oauth.py']:
            shutil.copy(MAIL_DIR / filename, root / filename)
        (root / 'mail.env').write_text(f'MAIL_OUTLOOK_USER={self.sender}\n')
        (root / 'body.txt').write_text('Crediti già acquisiti', encoding='utf-8')
        result = subprocess.run([sys.executable, str(root / 'mail_send.py'), 'outlook',
                                 '--to', self.recipients[0], '--subject', 'Test subject',
                                 '--body-file', str(root / 'body.txt'), '--dry-run'],
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(f'From: {self.sender}', result.stdout)
        self.assertIn('Subject: Test subject', result.stdout)
        self.assertFalse((root / 'outlook_tokens.json').exists())
        self.assertFalse((root / 'data').exists())


if __name__ == '__main__':
    unittest.main()
