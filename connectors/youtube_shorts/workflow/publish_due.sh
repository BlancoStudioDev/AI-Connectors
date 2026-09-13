#!/usr/bin/env bash
# Pubblica il video approvato allo slot orario: arg 1 = uscita 10:00, arg 2 = uscita 14:00.
set -uo pipefail
ROOT="$HOME/youtube-shorts-workflow"
PY="$HOME/agent-scripts/.venv/bin/python"
LOGDIR="$ROOT/data/logs"
mkdir -p "$LOGDIR"

SLOT="${1:-1}"
export DISPLAY=:99
if ! pgrep -x Xvfb >/dev/null; then (Xvfb :99 -screen 0 1366x850x24 >/dev/null 2>&1 &); sleep 2; fi

exec 8>"$ROOT/data/publish.lock"
flock -n 8 || { echo "publish già in esecuzione"; exit 0; }

TS=$(TZ=Europe/Rome date +%Y%m%d_%H%M)
LOG="$LOGDIR/publish_${SLOT}_$TS.log"
exec >> "$LOG" 2>&1
echo "===== PUBLISH slot $SLOT $TS ====="

ORA=$([ "$SLOT" = "1" ] && echo "10:00" || echo "14:00")

# scegli il primo video approvato non ancora pubblicato
RUN=$("$PY" - "$SLOT" << 'EOF'
import json, sys
f = '/home/blanco05/youtube-shorts-workflow/data/morning.json'
d = json.load(open(f))
from datetime import datetime
from zoneinfo import ZoneInfo
today = datetime.now(ZoneInfo('Europe/Rome')).strftime('%Y-%m-%d')
if d.get('date') != today:
    print('NODATA'); sys.exit()
v = next((x for x in d['videos'] if x.get('status') == 'approved' and not x.get('published')), None)
print(v['run'] if v else 'NONE')
EOF
)

if [ "$RUN" = "NODATA" ]; then
  "$PY" notify.py "⏭️ $ORA — nessuna generazione stamattina, niente da pubblicare"
  echo "nessun dato"; exit 0
fi
if [ "$RUN" = "NONE" ]; then
  "$PY" notify.py "⏭️ $ORA — nessun video approvato da pubblicare. Puoi comunque approvarlo ora con Paloma: esce al prossimo slot."
  echo "nessun approvato"; exit 0
fi

TITOLO=$("$PY" -c "import json;print(json.load(open('$RUN/script.json'))['yt_title'])")
echo "pubblico: $RUN"

if OUT=$("$PY" 03_upload_youtube.py --outdir "$RUN"); then
  LINK=$(echo "$OUT" | tail -1 | sed 's/^UPLOAD OK //')
  "$PY" - "$SLOT" "$RUN" << 'EOF'
import json, sys
f = '/home/blanco05/youtube-shorts-workflow/data/morning.json'
d = json.load(open(f))
v = next(x for x in d['videos'] if x.get('run') == sys.argv[2])
v['published'] = True
v['published_at'] = '10:00' if sys.argv[1] == '1' else '14:00'
json.dump(d, open(f, 'w'), ensure_ascii=False, indent=1)
EOF
  "$PY" notify.py "🚀 Short pubblicato ($ORA): \"$TITOLO\"
$LINK"
  echo "pubblicato: $LINK"
else
  "$PY" notify.py "❌ $ORA — upload fallito per \"$TITOLO\" (log: $LOG)"
  echo "upload fallito"
  exit 1
fi
