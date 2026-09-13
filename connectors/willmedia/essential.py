#!/usr/bin/env python3
"""Skill ESSENTIAL — scarica e invia in chat l'ultimo "The Essential" di Will Media.

Ogni giorno (via cron) cerca il video più recente del canale YouTube di Will Media
con "The Essential" nel titolo, lo scarica (scraping yt-dlp, NESSUNA API ufficiale
Google) e lo invia in chat Telegram:
  - <= 48 MB  -> Bot API (sendVideo, streaming immediato)
  - > 48 MB   -> Telethon con l'account reale ( verso la chat del bot)

Uso:
  essential.py            -> controlla e invia se c'e' un nuovo video
  essential.py --force    -> scarica e invia anche se già inviato (per test)
  essential.py --status   -> mostra l'ultimo inviato

Stato: data/essential_state.json
"""
import json
import os
import subprocess
import sys
import urllib.request
import urllib.parse
from pathlib import Path

BASE = Path(__file__).resolve().parent
DATA = BASE / "data"
STATE = DATA / "essential_state.json"
CHANNEL_RSS = "https://www.youtube.com/feeds/videos.xml?channel_id=UCZM5aON36Iw0o0ngTaQSWVA"
MARKER = "The Essential"
CHAT_ID = os.environ.get("ESSENTIAL_CHAT_ID", "937399076")
BOT_CHAT = "blancostudiodev_bot"
MAX_BOT_BYTES = 48_000_000
YTDLP = str(BASE / ".venv" / "bin" / "yt-dlp")
ENV_BOT = Path.home() / "telegram-agent" / ".env"


def load_env(path):
    env = {}
    if path.exists():
        for line in path.read_text().splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    return env


def run(cmd, timeout=600):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def find_latest():
    # Rilevamento via RSS ufficiale del canale: istantaneo e imscrapable
    import xml.etree.ElementTree as ET
    ATOM = "{http://www.w3.org/2005/Atom}"
    YT = "{http://www.youtube.com/xml/schemas/2015}"
    with urllib.request.urlopen(CHANNEL_RSS, timeout=30) as r:
        root = ET.fromstring(r.read())
    for e in root.iter(ATOM + "entry"):
        vid_el, title_el = e.find(YT + "videoId"), e.find(ATOM + "title")
        if vid_el is None or title_el is None:
            continue
        title = title_el.text or ""
        if MARKER.lower() in title.lower():
            return vid_el.text, title.strip()
    sys.exit("nessun The Essential nel feed RSS del canale")


def download(vid):
    out = f"/tmp/essential_{vid}.mp4"
    url = f"https://www.youtube.com/watch?v={vid}"
    r = run([YTDLP, "-q", "--no-warnings", "--ffmpeg-location", str(BASE / "bin" / "ffmpeg"),
             "-f", "bv*[vcodec^=avc1][height<=720]+ba[acodec^=mp4a]/b[vcodec^=avc1][height<=720]/b[height<=720][ext=mp4]/bv*+ba/b",
             "--merge-output-format", "mp4", "-o", out, url], timeout=1800)
    if r.returncode != 0 or not os.path.exists(out):
        sys.exit(f"download fallito: {r.stderr[-400:]}")
    return out


def send_bot_api(path, title):
    """Invio via Bot API (streaming immediato) se il file e' piccolo."""
    env = load_env(ENV_BOT)
    token = env.get("BOT_TOKEN")
    if not token:
        return False
    url = f"https://api.telegram.org/bot{token}/sendVideo"
    boundary = "----essential1234"
    with open(path, "rb") as f:
        video = f.read()
    parts = [
        ("chat_id", CHAT_ID),
        ("caption", f"📺 The Essential — Will Media\n{title}"),
        ("supports_streaming", "true"),
    ]
    body = b""
    for k, v in parts:
        body += (f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n").encode()
    body += (f"--{boundary}\r\nContent-Disposition: form-data; name=\"video\"; filename=\"essential.mp4\"\r\n"
             "Content-Type: video/mp4\r\n\r\n").encode() + video + b"\r\n"
    body += f"--{boundary}--\r\n".encode()
    req = urllib.request.Request(url, data=body, headers={
        "Content-Type": f"multipart/form-data; boundary={boundary}"})
    try:
        with urllib.request.urlopen(req, timeout=600) as resp:
            ok = json.loads(resp.read()).get("ok")
        return bool(ok)
    except Exception as e:
        print("Bot API sendVideo fallito:", str(e)[:200])
        return False


def send_telethon(path, title):
    """Fallback: invio come account reale nella chat del bot (o in Messaggi salvati)."""
    env = load_env(BASE / ".env")
    from telethon.sync import TelegramClient
    from telethon.sessions import StringSession
    with TelegramClient(str(BASE / "tg_session"),
                        int(env["TG_API_ID"]), env["TG_API_HASH"]) as c:
        try:
            ent = c.get_entity(BOT_CHAT)
        except Exception:
            ent = "me"
        c.send_file(ent, path, caption=f"📺 The Essential — Will Media\n{title}",
                    supports_streaming=True, force_document=False)


def main():
    force = "--force" in sys.argv
    DATA.mkdir(parents=True, exist_ok=True)
    state = {}
    if STATE.exists():
        try:
            state = json.loads(STATE.read_text())
        except Exception:
            state = {}

    if "--status" in sys.argv:
        print("ultimo inviato:", json.dumps(state, ensure_ascii=False))
        return

    vid, title = find_latest()
    if not force and state.get("last_id") == vid:
        print(f"nessun nuovo Essential (ultimo: {vid})")
        return

    print("trovato nuovo video:", vid, "|", title)
    path = download(vid)
    size = os.path.getsize(path)
    print(f"scaricato: {size/1_000_000:.1f} MB")

    sent = send_bot_api(path, title) if size <= MAX_BOT_BYTES else False
    if not sent:
        print("invio via Telethon (account reale)...")
        send_telethon(path, title)

    state.update({"last_id": vid, "title": title, "sent": True})
    STATE.write_text(json.dumps(state, indent=1, ensure_ascii=False))
    os.remove(path)
    print("✅ inviato e registrato:", vid)


if __name__ == "__main__":
    main()
