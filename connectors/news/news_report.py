#!/usr/bin/env python3
"""Report news del giorno da feed RSS (nessuna chiave API)."""
import re, requests, feedparser
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Rome")
FEEDS = {
    "Prima pagina": [
        ("ANSA Top News", "https://www.ansa.it/sito/notizie/topnews/topnews_rss.xml"),
        ("ANSA Ultima Ora", "https://www.ansa.it/sito/ansait_rss.xml"),
    ],
    "Tech": [
        ("ANSA Tecnologia", "https://www.ansa.it/canale_tecnologia/tecnologia_rss.xml"),
        ("Hacker News", "https://hnrss.org/frontpage"),
        ("The Verge", "https://www.theverge.com/rss/index.xml"),
    ],
    "Scienza": [
        ("ANSA Scienza", "https://www.ansa.it/canale_scienza_tecnica/notizie/scienza_tecnica_rss.xml"),
    ],
}

def clean(s, n=160):
    s = re.sub(r"<[^>]+>", " ", s or "")
    s = re.sub(r"\s+", " ", s).strip()
    return s[:n].rstrip() + ("…" if len(s) > n else "")

def main():
    now = datetime.now(TZ)
    cutoff = now - timedelta(hours=20)
    for cat, sources in FEEDS.items():
        items = []
        for name, url in sources:
            try:
                r = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
                d = feedparser.parse(r.content)
                for e in d.entries[:40]:
                    dt = None
                    for attr in ("published_parsed", "updated_parsed"):
                        t = getattr(e, attr, None)
                        if t:
                            dt = datetime(*t[:6], tzinfo=TZ)
                            break
                    if dt is None or dt < cutoff:
                        continue
                    items.append((dt, name, e.get("title", "").strip(), clean(e.get("summary", ""))))
            except Exception as ex:
                print(f"ERR {name}: {ex}")
        items.sort(key=lambda x: x[0], reverse=True)
        print(f"\n===== {cat} =====")
        seen = set()
        count = 0
        for dt, src, title, summ in items:
            key = title.lower()[:60]
            if key in seen:
                continue
            seen.add(key)
            print(f"[{dt.strftime('%H:%M')}] {title}  ({src})")
            if summ:
                print(f"   {summ}")
            count += 1
            if count >= 12:
                break
        if not items:
            print("(nessuna news nelle ultime 20h)")

if __name__ == "__main__":
    main()
