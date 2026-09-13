#!/usr/bin/env bash
# Tick ogni 5 minuti (cron). Fuso Europe/Rome:
#   07:00 -> morning_run.sh   (genera 2 video, li manda su Telegram)
#   09:30 -> promemoria se nessun video ancora approvato
#   10:00 -> publish_due.sh 1 (pubblica il 1° approvato)
#   14:00 -> publish_due.sh 2 (pubblica il 2° approvato)
ROOT="$HOME/youtube-shorts-workflow"
ST="$ROOT/data"

HH=$(TZ=Europe/Rome date +%H)
MM=$(TZ=Europe/Rome date +%M)
DAY=$(TZ=Europe/Rome date +%F)

fire() { # $1 = nome guardia, $2 = finestra minuti, resto = comando
  local name="$1"; shift
  local win="$1"; shift
  [ "$MM" -lt "$win" ] || return 0
  local last
  last=$(cat "$ST/guard_$name" 2>/dev/null)
  if [ "$last" = "$DAY" ]; then return 0; fi
  echo "$DAY" > "$ST/guard_$name"
  "$@"
}

case "$HH" in
  07) fire morning 15 "$ROOT/morning_run.sh" >> "$ST/logs/tick_morning.log" 2>&1 ;;
  09) if [ "$MM" -ge 30 ] && [ "$MM" -lt 35 ]; then
        last=$(cat "$ST/guard_remind" 2>/dev/null)
        if [ "$last" != "$DAY" ]; then
          echo "$DAY" > "$ST/guard_remind"
          "$HOME/agent-scripts/.venv/bin/python" - << 'EOF' >> "$ST/logs/tick_remind.log" 2>&1
import json
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path
import sys
sys.path.insert(0, '/home/blanco05/youtube-shorts-workflow')
try:
    d = json.load(open('/home/blanco05/youtube-shorts-workflow/data/morning.json'))
    today = datetime.now(ZoneInfo('Europe/Rome')).strftime('%Y-%m-%d')
    pend = [v for v in d.get('videos', []) if v.get('status') == 'pending' and v.get('video')]
    if d.get('date') == today and pend and not any(v.get('status') == 'approved' for v in d['videos']):
        import subprocess
        subprocess.run(['/home/blanco05/agent-scripts/.venv/bin/python',
                        '/home/blanco05/youtube-shorts-workflow/notify.py',
                        '⏰ Promemoria: i 2 video di oggi aspettano il tuo giudizio. Dimmi ad esempio "approva 1" o "scarta 2".'])
except Exception:
    pass
EOF
      fi
    fi ;;
  10) fire pub1 15 "$ROOT/publish_due.sh" 1 >> "$ST/logs/tick_pub1.log" 2>&1 ;;
  14) fire pub2 15 "$ROOT/publish_due.sh" 2 >> "$ST/logs/tick_pub2.log" 2>&1 ;;
esac
