#!/usr/bin/env python3
"""Esegue news_report.py e invia il report mattutino come file .md in chat Telegram."""
import subprocess, json, requests
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

HERE = Path(__file__).parent
TG_DIR = Path('/home/blanco05/telegram-agent')
TZ = ZoneInfo("Europe/Rome")

def bot_token():
    for line in (TG_DIR / '.env').read_text().splitlines():
        if line.strip().startswith('BOT_TOKEN='):
            return line.split('=', 1)[1].strip()

def main():
    r = subprocess.run(['/home/blanco05/agent-scripts/.venv/bin/python', str(HERE / 'news_report.py')],
                       capture_output=True, text=True, timeout=180)
    out = (r.stdout or '').strip()
    if not out:
        out = "Nessuna news trovata (feed non raggiungibili)."
        print(r.stderr[-500:])
    now = datetime.now(TZ)
    giorni = ['lunedì','martedì','mercoledì','giovedì','venerdì','sabato','domenica']
    titolo = f"Report del mattino — {giorni[now.weekday()]} {now.strftime('%d/%m/%Y')}"
    md = f"# 📰 {titolo}\n\n{out}\n\n---\n_Generato da Paloma alle {now.strftime('%H:%M')}_\n"
    fpath = Path(f"/tmp/report_mattina_{now.strftime('%Y%m%d')}.md")
    fpath.write_text(md, encoding='utf-8')
    token = bot_token()
    chat = json.load(open(TG_DIR / 'admin.json'))[0]
    with open(fpath, 'rb') as f:
        resp = requests.post(
            f"https://api.telegram.org/bot{token}/sendDocument",
            data={'chat_id': chat, 'caption': f"📰 {titolo} — in allegato il file .md"},
            files={'document': (fpath.name, f, 'text/markdown')}, timeout=120)
    print('sendDocument:', resp.json().get('ok'), resp.json().get('description', ''))

if __name__ == '__main__':
    main()
