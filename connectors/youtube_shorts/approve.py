#!/usr/bin/env python3
"""Approvazione video del mattino (usata da Paloma o a mano).
Uso:
  approve.py status          -> stato del giorno
  approve.py <1|2> ok        -> approva il video N
  approve.py <1|2> no        -> scarta il video N
Il primo approvato viene pubblicato alle 10:00, il secondo alle 14:00.
"""
import fcntl, json, sys
from pathlib import Path

STATE = Path(__file__).parent / 'data' / 'morning.json'


def load():
    try:
        return json.load(open(STATE))
    except Exception:
        return {'date': None, 'videos': []}


def save(d):
    STATE.write_text(json.dumps(d, ensure_ascii=False, indent=1))


def status_text(d):
    from datetime import datetime
    from zoneinfo import ZoneInfo
    today = datetime.now(ZoneInfo('Europe/Rome')).strftime('%Y-%m-%d')
    if d.get('date') != today or not d.get('videos'):
        return 'Nessun video generato stamattina.'
    approved = [v for v in d['videos'] if v.get('status') == 'approved']
    out = ['📋 Video di oggi:']
    for v in d['videos']:
        st = {'pending': '⏳ in attesa', 'approved': '✅ approvato',
              'rejected': '❌ scartato', 'failed': '⚠️ generazione fallita',
              'published': '🚀 pubblicato'}.get(v.get('status'), v.get('status', '?'))
        out.append(f"  {v['slot']}/2 — {st} — {v.get('title', '(nessun titolo)')}")
    if approved:
        if len(approved) >= 1:
            out.append('→ in uscita alle 10:00: video ' + str(approved[0]['slot']))
        if len(approved) >= 2:
            out.append('→ in uscita alle 14:00: video ' + str(approved[1]['slot']))
    else:
        out.append('→ nessun video approvato: alle 10:00 non pubblica nulla')
    return '\n'.join(out)


def main():
    lock = open(Path(__file__).parent / 'data' / 'morning.lock', 'w')
    fcntl.flock(lock, fcntl.LOCK_EX)
    d = load()
    if len(sys.argv) < 2 or sys.argv[1] == 'status':
        print(status_text(d))
        return
    slot = sys.argv[1]
    if slot not in ('1', '2') or len(sys.argv) < 3 or sys.argv[2] not in ('ok', 'no'):
        print('uso: approve.py <1|2> <ok|no> | status')
        return
    v = next((x for x in d.get('videos', []) if str(x.get('slot')) == slot), None)
    if not v or not v.get('video') or v.get('status') == 'failed':
        print(f'Il video {slot} non esiste (generazione fallita o non ancora fatto).')
        return
    if v.get('published'):
        print(f'Il video {slot} è già stato pubblicato.')
        return
    v['status'] = 'approved' if sys.argv[2] == 'ok' else 'rejected'
    save(d)
    approved = [x for x in d['videos'] if x.get('status') == 'approved']
    n = len(approved)
    if v['status'] == 'approved':
        ora = '10:00' if n == 1 else '14:00' if n == 2 else '(coda extra)'
        print(f'✅ Video {slot} approvato — sarà pubblicato alle {ora}: "{v.get("title", "")}"')
    else:
        print(f'❌ Video {slot} scartato. Per rigenerarlo: "rigenera {slot}".')
    print(status_text(d))


if __name__ == '__main__':
    main()
