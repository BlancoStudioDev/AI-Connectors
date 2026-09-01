#!/usr/bin/env bash
# AI-Connectors — set up ~/agent-scripts on the agent's host/server.
# Copies the scripts, creates the shared venv and prints the .env checklist.
set -euo pipefail

DEST="${HOME}/agent-scripts"
SRC="$(cd "$(dirname "$0")" && pwd)/connectors"

mkdir -p "$DEST/data"
chmod 700 "$DEST"

cp "$SRC/mail/mail.py" "$DEST/"
cp "$SRC/mail/msft_login.py" "$DEST/" 2>/dev/null || true
cp "$SRC/calendar/cal.py" "$DEST/"
cp "$SRC/strava/strava.py" "$DEST/"
cp "$SRC/strava/strava_login.py" "$DEST/"
cp "$SRC/meteo/meteo.py" "$DEST/"
cp "$SRC/nutri/nutri.py" "$DEST/"
cp "$SRC/clima/ac.py" "$DEST/"
cp "$SRC/whatsapp/wa.py" "$DEST/"
cp "$SRC/telegram/telegram.py" "$DEST/"

if [ ! -d "$DEST/.venv" ]; then
  python3 -m venv "$DEST/.venv"
fi
"$DEST/.venv/bin/pip" install -q --upgrade pip
"$DEST/.venv/bin/pip" install -q imap-tools caldav vobject requests telethon

touch "$DEST/.env"
chmod 600 "$DEST/.env"
touch "$DEST/mail.env"
chmod 600 "$DEST/mail.env"

echo
echo "✅ Scripts installed in $DEST"
echo "✅ Venv ready: $DEST/.venv (imap-tools, caldav, vobject, requests, telethon)"
echo
echo "Next steps — fill in the credentials (files already have permission 600):"
echo "  1) $DEST/.env      → APPLE_EMAIL, ICLOUD_APP_PASSWORD, STRAVA_CLIENT_ID/SECRET,"
echo "                        ZAI_API_KEY (optional), HI_SMARTLIFE_USER/PASS,"
echo "                        TG_API_ID/TG_API_HASH/TG_PHONE, WA_API_URL (optional)"
echo "  2) $DEST/mail.env  → MAIL_<account>_HOST/USER/PASS for each IMAP account"
echo "  3) One-shot logins where needed:"
echo "       $DEST/.venv/bin/python $DEST/msft_login.py          (OAuth mail)"
echo "       $DEST/.venv/bin/python $DEST/telegram.py login      (Telegram session)"
echo "       Strava: open the authorization URL, then strava_login.py <code>"
echo "  4) Paste the skill block from docs/system-prompt.md into your agent's system prompt"
echo "  5) Test every connector manually first, e.g.: $DEST/.venv/bin/python $DEST/meteo.py now Milan"
