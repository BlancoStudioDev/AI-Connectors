#!/usr/bin/env bash
# Generazione mattina: 2 video storici alle 7:00, inviati a Paloma su Telegram.
# Uso: morning_run.sh            (genera i video mancanti del giorno)
#      morning_run.sh regen <1|2> (rigenera uno slot e lo reinvia)
set -uo pipefail
ROOT="$HOME/youtube-shorts-workflow"
PY="$HOME/agent-scripts/.venv/bin/python"
LOGDIR="$ROOT/data/logs"
mkdir -p "$LOGDIR"

export DISPLAY=:99
if ! pgrep -x Xvfb >/dev/null; then (Xvfb :99 -screen 0 1366x850x24 >/dev/null 2>&1 &); sleep 2; fi

exec 9>"$ROOT/data/morning.lock"
flock -n 9 || { echo "morning già in esecuzione"; exit 0; }

TS=$(TZ=Europe/Rome date +%Y%m%d_%H%M)
LOG="$LOGDIR/morning_$TS.log"
exec >> "$LOG" 2>&1
echo "===== MORNING $TS (args: $*) ====="
cd "$ROOT"

REGEN_SLOT="${2:-}"
if [ "${1:-}" = "regen" ] && [ -z "$REGEN_SLOT" ]; then echo "slot mancante"; exit 1; fi

# stato del giorno
"$PY" - "$REGEN_SLOT" << 'EOF'
import json, sys
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path
STATE = Path('/home/blanco05/youtube-shorts-workflow/data/morning.json')
today = datetime.now(ZoneInfo('Europe/Rome')).strftime('%Y-%m-%d')
try:
    d = json.load(open(STATE))
except Exception:
    d = {}
regen = sys.argv[1] if len(sys.argv) > 1 and sys.argv[1] else ''
if d.get('date') != today or not d.get('videos'):
    d = {'date': today, 'videos': [
        {'slot': 1, 'status': 'pending', 'run': '', 'title': '', 'video': '', 'published': False},
        {'slot': 2, 'status': 'pending', 'run': '', 'title': '', 'video': '', 'published': False}]}
for v in d['videos']:
    if regen and str(v['slot']) == regen and not v.get('published'):
        v['status'] = 'pending'; v['run'] = ''; v['video'] = ''; v['title'] = ''
STATE.write_text(json.dumps(d, ensure_ascii=False, indent=1))
EOF

FAILED=0
for SLOT in 1 2; do
  SKIP=$("$PY" - "$SLOT" << 'EOF'
import json, sys
d = json.load(open('/home/blanco05/youtube-shorts-workflow/data/morning.json'))
v = next((x for x in d['videos'] if str(x['slot']) == sys.argv[1]), {})
print('skip' if v.get('video') else 'todo')
EOF
)
  if [ "$SKIP" = "skip" ]; then echo "slot $SLOT già pronto"; continue; fi

  RUN="$ROOT/data/output/${TS}_slot${SLOT}"
  echo "--- slot $SLOT: generazione ---"
  if ! "$PY" 01_generate_script.py --outdir "$RUN"; then
    "$PY" notify.py "❌ Video $SLOT/2 di oggi: generazione script fallita"
    "$PY" - "$SLOT" << 'EOF'
import json, sys
f = '/home/blanco05/youtube-shorts-workflow/data/morning.json'
d = json.load(open(f))
next(x for x in d['videos'] if str(x['slot']) == sys.argv[1])['status'] = 'failed'
json.dump(d, open(f, 'w'), ensure_ascii=False, indent=1)
EOF
    FAILED=1
    continue
  fi
  if ! "$PY" 02_make_video.py --outdir "$RUN"; then
    "$PY" notify.py "❌ Video $SLOT/2 di oggi: creazione video fallita (log: $LOG)"
    "$PY" - "$SLOT" << 'EOF'
import json, sys
f = '/home/blanco05/youtube-shorts-workflow/data/morning.json'
d = json.load(open(f))
next(x for x in d['videos'] if str(x['slot']) == sys.argv[1])['status'] = 'failed'
json.dump(d, open(f, 'w'), ensure_ascii=False, indent=1)
EOF
    FAILED=1
    continue
  fi

  TITOLO=$("$PY" -c "import json;print(json.load(open('$RUN/script.json'))['yt_title'])")
  TEMA=$("$PY" -c "import json;print(json.load(open('$RUN/script.json'))['topic'])")
  "$PY" - "$SLOT" "$RUN" "$TITOLO" << 'EOF'
import json, sys
f = '/home/blanco05/youtube-shorts-workflow/data/morning.json'
d = json.load(open(f))
slot, run, title = sys.argv[1], sys.argv[2], sys.argv[3]
v = next(x for x in d['videos'] if str(x['slot']) == slot)
v.update({'run': run, 'title': title, 'video': run + '/video.mp4', 'status': 'pending'})
json.dump(d, open(f, 'w'), ensure_ascii=False, indent=1)
EOF

  CAPTION="🎬 Video ${SLOT}/2 di oggi (tema: ${TEMA})

«${TITOLO}»

✅ Va bene? Dimmi \"approva ${SLOT}\"
❌ Da rifare? Dimmi \"scarta ${SLOT}\" o \"rigenera ${SLOT}\"

📅 Approvato n.1 → pubblicazione 10:00 | n.2 → 14:00"
  if "$PY" send_video.py "$RUN/video.mp4" "$CAPTION"; then
    echo "slot $SLOT inviato"
  else
    "$PY" notify.py "⚠️ Non riesco a inviare il video ${SLOT}/2 su Telegram (log: $LOG)"
    FAILED=1
  fi
done

if [ "$FAILED" = "0" ]; then
  echo "morning completata"
fi
