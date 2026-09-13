#!/usr/bin/env bash
# Workflow YouTube Shorts: script (DeepSeek) -> video (Invideo AI) -> upload (YouTube)
set -uo pipefail
ROOT="$HOME/youtube-shorts-workflow"
PY="$HOME/agent-scripts/.venv/bin/python"
LOGDIR="$ROOT/data/logs"
mkdir -p "$LOGDIR"

# display virtuale per i login Google (headful)
if ! pgrep -x Xvfb >/dev/null; then
  (Xvfb :99 -screen 0 1366x850x24 >/dev/null 2>&1 &)
  sleep 2
fi
export DISPLAY=:99

exec 9>"$ROOT/data/lock"
flock -n 9 || { echo "già in esecuzione"; exit 0; }

TS=$(TZ=Europe/Rome date +%Y%m%d_%H%M)
RUN="$ROOT/data/output/$TS"
LOG="$LOGDIR/run_$TS.log"
exec >> "$LOG" 2>&1

echo "===== RUN $TS ====="
cd "$ROOT"

if ! "$PY" 01_generate_script.py --outdir "$RUN"; then
  "$PY" notify.py "❌ Shorts $TS: generazione script fallita (log: $LOG)"
  exit 1
fi

if ! "$PY" 02_make_video.py --outdir "$RUN"; then
  "$PY" notify.py "⚠️ Shorts $TS: script pronto ma la creazione video è fallita (log: $LOG)"
  exit 1
fi

TITOLO=$("$PY" -c "import json;print(json.load(open('$RUN/script.json'))['yt_title'])")
if ! OUT=$("$PY" 03_upload_youtube.py --outdir "$RUN"); then
  "$PY" notify.py "⚠️ Short \"$TITOLO\" creato ma upload YouTube fallito. Video: $RUN/video.mp4"
  exit 1
fi
LINK=$(echo "$OUT" | tail -1 | sed 's/^UPLOAD OK //')
"$PY" notify.py "✅ Short pubblicato: \"$TITOLO\"
$LINK"
echo "===== DONE $TS ====="
