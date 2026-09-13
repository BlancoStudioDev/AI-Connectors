#!/usr/bin/env python3
"""
news.py — Skill NEWS: news della giornata + analisi direzioni di lungo periodo.

Comandi:
  today                       Scarica le news di oggi (RSS: mondo + economia)
  ingest [--days N|--date D]  Classifica le news con LLM e le salva nel DB (storico)
  brief [--days N]            Digest LLM della giornata: mondo, economia, direzioni
  trend "TERMINE" [--days N]  Direzione di lungo periodo per azienda/tema/sector
  query "testo" [--days N]    Ricerca nello storico classificato
  db                          Statistiche dello storico
"""
import argparse, asyncio, importlib.util, json, os, re, sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
import xml.etree.ElementTree as ET

import httpx
from dotenv import load_dotenv

HOME = Path.home()
SCRIPT_DIR = HOME / "agent-scripts"
DATA_DIR = SCRIPT_DIR / "news_data"
REPO_DIR = HOME / "News-Evaluator"
DB_URL = f"sqlite+aiosqlite:///{REPO_DIR}/data/news.db"
TZ = timezone(timedelta(hours=2))  # Europe/Rome CEST
sys.path.insert(0, str(REPO_DIR))

load_dotenv(SCRIPT_DIR / ".env")
os.environ.setdefault("DATABASE_URL", DB_URL)

FEEDS = {
    "ansa_mondo":         "https://www.ansa.it/sito/notizie/mondo/mondo_rss.xml",
    "ansa_economia":      "https://www.ansa.it/sito/notizie/economia/economia_rss.xml",
    "guardian_world":     "https://www.theguardian.com/world/rss",
    "guardian_business":  "https://www.theguardian.com/uk/business/rss",
    "bbc_world":          "https://feeds.bbci.co.uk/news/world/rss.xml",
    "bbc_business":       "https://feeds.bbci.co.uk/news/business/rss.xml",
    "sole24ore_economia": "https://www.ilsole24ore.com/rss/economia.xml",
    "marketwatch":        "https://feeds.content.dowjones.io/public/rss/mw_topstories",
    "repubblica_economia":"https://www.repubblica.it/rss/economia/rss2.0.xml",
    "yahoo_finance":      "https://finance.yahoo.com/news/rssindex",
}
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"}
CENC = "{http://purl.org/rss/1.0/modules/content/}encoded"


def strip_html(s: str) -> str:
    s = re.sub(r"<[^>]+>", " ", s or "")
    s = re.sub(r"&[a-z]+;", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def parse_rss(xml_text: str) -> list[dict]:
    try:
        root = ET.fromstring(xml_text.encode("utf-8"))
    except ET.ParseError:
        return []
    out = []
    for item in root.iter("item"):
        title = strip_html(item.findtext("title") or "")
        link = (item.findtext("link") or "").strip()
        if not title or not link:
            continue
        content = strip_html(item.find(CENC).text if item.find(CENC) is not None else None)
        if len(content) < 60:
            content = strip_html(item.findtext("description") or "")
        pub = item.findtext("pubDate")
        published_at = None
        if pub:
            try:
                published_at = parsedate_to_datetime(pub).isoformat()
            except Exception:
                pass
        out.append({"title": title, "content": content[:3000] or None, "link": link,
                    "published_at": published_at})
    return out


def fetch_feed(name: str, url: str) -> tuple[str, list[dict]]:
    try:
        r = httpx.get(url, headers=UA, timeout=20, follow_redirects=True)
        r.raise_for_status()
        return name, parse_rss(r.text)
    except Exception as e:
        print(f"  ⚠ {name}: {type(e).__name__}: {e}", file=sys.stderr)
        return name, []


def cmd_today(args):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    today = datetime.now(TZ).strftime("%Y-%m-%d")
    day_dir = DATA_DIR / today
    day_dir.mkdir(exist_ok=True)
    results, all_arts = {}, []
    with ThreadPoolExecutor(max_workers=10) as ex:
        for name, arts in ex.map(lambda kv: fetch_feed(*kv), FEEDS.items()):
            results[name] = len(arts)
            for a in arts:
                a["source"] = name
            all_arts.extend(arts)
            (day_dir / f"{name}.json").write_text(
                json.dumps({"fetched_at": datetime.now(TZ).isoformat(), "source": name,
                            "articles": arts}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"📰 News di oggi ({today}): {len(all_arts)} articoli")
    for name, n in results.items():
        print(f"  • {name}: {n}")
    print("\n— Titoli in evidenza —")
    for a in all_arts[:14]:
        print(f"  [{a['source']}] {a['title'][:110]}")


def _collect_articles(days: int, date: str | None) -> list[dict]:
    arts, seen = [], set()
    if date:
        dates = [date]
    else:
        now = datetime.now(TZ)
        dates = [(now - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(days)]
    for d in dates:
        dd = DATA_DIR / d
        if not dd.is_dir():
            continue
        for f in sorted(dd.glob("*.json")):
            try:
                for a in json.loads(f.read_text())["articles"]:
                    if a["link"] and a["link"] not in seen:
                        seen.add(a["link"])
                        arts.append(a)
            except Exception:
                pass
    return arts


def cmd_ingest(args):
    arts = _collect_articles(args.days, args.date)
    if not arts:
        print("Nessun articolo scaricato. Esegui prima: news.py today")
        return
    # stub embedder se chromadb non è installato (embedding è non-critico nel pipeline)
    try:
        import chromadb  # noqa
    except ImportError:
        import types
        stub = types.ModuleType("newssystem.embedder")
        stub.store_article_embedding = lambda *a, **k: None
        sys.modules["newssystem.embedder"] = stub
    spec = importlib.util.spec_from_file_location("ingest_scraped", REPO_DIR / "scripts" / "ingest_scraped.py")
    mod = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(REPO_DIR))
    spec.loader.exec_module(mod)
    from newssystem.database import init_db
    asyncio.run(init_db())  # crea le tabelle se non esistono
    print(f"Invio {len(arts)} articoli alla pipeline LLM (classificazione + scoring)…")
    res = asyncio.run(mod.ingest_direct(arts, concurrency=8))
    print(f"✅ Ingest completato: {res}")


def _llm(system: str, user: str, max_tokens: int = 2200) -> str:
    base = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
    r = httpx.post(f"{base}/chat/completions",
                   headers={"Authorization": f"Bearer {os.environ['DEEPSEEK_API_KEY']}"},
                   json={"model": os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
                         "messages": [{"role": "system", "content": system},
                                      {"role": "user", "content": user}],
                         "temperature": 0.3, "max_tokens": max_tokens},
                   timeout=180)
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]


def _load_for_brief(days: int) -> list[dict]:
    # prova prima il DB (classificato), poi fallback sui file
    try:
        sys.path.insert(0, str(REPO_DIR))
        from newssystem.database import Article, async_session
        from sqlalchemy import select
        cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days)
        arts = asyncio.run(_db_articles(cutoff))
        if len(arts) >= 5:
            return [{"source": a.source, "title": a.title,
                     "content": (a.content or "")[:220],
                     "published_at": str(a.published_at or "")} for a in arts]
    except Exception:
        pass
    return [{"source": a["source"], "title": a["title"], "content": a["content"] or "",
             "published_at": a.get("published_at") or ""} for a in _collect_articles(days, None)]


async def _db_articles(cutoff, like=None, limit=400):
    from newssystem.database import Article, async_session
    from sqlalchemy import select, or_
    async with async_session() as s:
        q = select(Article).where(Article.published_at >= cutoff).order_by(Article.score.desc())
        if like:
            q = q.where(or_(Article.title.ilike(f"%{like}%"), Article.content.ilike(f"%{like}%")))
        q = q.limit(limit)
        res = await s.execute(q)
        return res.scalars().all()


def cmd_brief(args):
    arts = _load_for_brief(args.days)
    if not arts:
        print("Nessuna news. Esegui: news.py today")
        return
    lines = [f"- [{a['source']}] {a['title']}" + (f" — {a['content'][:220]}" if a.get("content") else "")
             for a in arts[:120]]
    user = (f"Queste sono le news raccolte negli ultimi {args.days} giorno/i ({len(arts)} articoli, "
            "fonti: ANSA, Guardian, BBC, Il Sole 24 Ore, MarketWatch, Repubblica, Yahoo Finance).\n\n"
            + "\n".join(lines)
            + "\n\nScrivi in ITALIANO un brief con esattamente queste sezioni markdown:\n"
              "### 🌍 Mondo — i 5-7 fatti più importanti (1 riga ciascuno)\n"
              "### 💶 Economia & Mercati — 5-7 punti chiave (macro, banche centrali, dati, mercati)\n"
              "### 📈 Direzioni di lungo periodo — quali settori/temi/aziende le notizie suggeriscono IN CRESCITA e quali IN CALO nel medio-lungo periodo, con il motivo (es. 'semiconduttori memoria ↑ per …'). Cita aziende concrete quando possibile.\n"
              "### ⚠️ Da tenere d'occhio — 2-3 rischi/catalizzatori futuri\n"
              "Sii concreto e specifico, niente frasi generiche.")
    print(_llm("Sei un analista di mercato senior che scrive brief giornalieri concisi e azionabili.", user))


def cmd_trend(args):
    term, days = args.term, args.days
    cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days)
    arts = asyncio.run(_db_articles(cutoff, like=term, limit=150))
    if not arts:
        # fallback: ricerca in tempo reale via Google News RSS
        gname, garts = fetch_feed("google_news",
            f"https://news.google.com/rss/search?q={httpx.QueryParams({'q': term}).get('q')}&hl=it&gl=IT&ceid=IT:it")
        if not garts:
            print(f"Nessun articolo che menziona '{term}' (né nello storico né su Google News).")
            print("Suggerimento: 'news.py today && news.py ingest' per popolare lo storico.")
            return
        print(f"(nessuna news nello storico classificato — analisi su {len(garts)} risultati freschi da Google News)")
        titles = "\n".join(f"- {a['title']}" for a in garts[:35])
        user = (f"Termine: '{term}'. Notizie recenti trovate su Google News:\n{titles}\n\n"
                "In italiano, dai una VALUTAZIONE DI DIREZIONE di lungo periodo per '" + term + "': "
                "🟢 in crescita / 🔴 in calo / 🟡 neutrale-attesa, con: 1) segnali dalle news (2-3 punti concreti), "
                "2) interpretazione di fondo (driver strutturali), 3) confidenza (bassa/media/alta), "
                "4) cosa confermerebbe o smentirebbe la tesi nei prossimi mesi. "
                "Concludi con: 'Nota: analisi qualitativa su news, non consulenza finanziaria.'")
        print(_llm("Sei un analista equity/macro senior. Ragioni dai dati forniti, senza inventare fatti non presenti.", user))
        return
    n = len(arts)
    sents = [a.sentiment_score for a in arts]
    avg_sent = sum(sents) / n
    pts = sorted(arts, key=lambda a: a.published_at or datetime.min.replace(tzinfo=timezone.utc))
    half = max(1, len(pts) // 2)
    s1 = sum(a.sentiment_score for a in pts[:half]) / half
    s2 = sum(a.sentiment_score for a in pts[half:]) / (len(pts) - half)
    from collections import Counter
    sectors = Counter()
    for a in arts:
        for f in ("energy", "materials", "industrials", "consumer_discretionary", "consumer_staples",
                  "health_care", "financials", "information_technology", "communication_services",
                  "utilities", "real_estate"):
            v = getattr(a, f"sector_{f}", 0) or 0
            if v > 0:
                sectors[f] += v
    top_sectors = ", ".join(f"{k}({v:.0f})" for k, v in sectors.most_common(4)) or "n/d"
    evs = Counter(a.event_type for a in arts).most_common(4)
    titles = "\n".join(f"- [{a.source}] ({a.sentiment_label}, sev={a.base_severity:.1f}) {a.title[:130]}" for a in arts[:40])
    user = (f"Termine analizzato: '{term}' — ultime {days} giorni, {n} articoli classificati.\n"
            f"Sentiment medio: {avg_sent:+.2f} (scala -1..+1) | Trend: prima metà {s1:+.2f} → seconda metà {s2:+.2f}\n"
            f"Settori più impattati (score cumulato): {top_sectors}\n"
            f"Tipi di evento: {', '.join(f'{k}({v})' for k, v in evs)}\n\n"
            f"Titoli principali:\n{titles}\n\n"
            f"In italiano, dai una VALUTAZIONE DI DIREZIONE di lungo periodo per '{term}': "
            "🟢 in crescita / 🔴 in calo / 🟡 neutrale-attesa, con: 1) i segnali dalle news (2-3 punti concreti), "
            "2) l'interpretazione di fondo (driver strutturali), 3) una stima di confidenza (bassa/media/alta) "
            "4) cosa confermerebbe o smentirebbe la tesi nei prossimi mesi. "
            "Concludi con una riga: 'Nota: analisi qualitativa su news, non consulenza finanziaria.'")
    print(_llm("Sei un analista equity/macro senior. Ragioni dai dati forniti, senza inventare fatti non presenti.", user))


def cmd_query(args):
    cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=args.days)
    arts = asyncio.run(_db_articles(cutoff, like=args.term, limit=args.limit))
    if not arts:
        print("Nessun risultato.")
        return
    for a in arts:
        d = (a.published_at.strftime("%Y-%m-%d") if a.published_at else "?")
        print(f"[{d}] ({a.source}, {a.sentiment_label}, score={a.score:.0f}) {a.title[:120]}")
        print(f"        {a.link[:120] if a.link else ''}")


def cmd_db(args):
    sys.path.insert(0, str(REPO_DIR))
    from newssystem.database import Article, MacroNews, async_session
    from sqlalchemy import select, func
    async def stats():
        async with async_session() as s:
            n = (await s.execute(select(func.count(Article.id)))).scalar()
            days = (await s.execute(select(func.date(Article.published_at), func.count())
                                    .group_by(func.date(Article.published_at))
                                    .order_by(func.date(Article.published_at).desc()).limit(14))).all()
            nm = (await s.execute(select(func.count(MacroNews.id)))).scalar()
            return n, days, nm
    n, days, nm = asyncio.run(stats())
    print(f"🗄 DB: {n} articoli classificati, {nm} macro-topic")
    for d, c in days:
        print(f"  {d}: {c} articoli")


def main():
    p = argparse.ArgumentParser(description="Skill NEWS")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("today").set_defaults(func=cmd_today)
    s = sub.add_parser("ingest"); s.add_argument("--days", type=int, default=1); s.add_argument("--date"); s.set_defaults(func=cmd_ingest)
    s = sub.add_parser("brief"); s.add_argument("--days", type=int, default=1); s.set_defaults(func=cmd_brief)
    s = sub.add_parser("trend"); s.add_argument("term"); s.add_argument("--days", type=int, default=90); s.set_defaults(func=cmd_trend)
    s = sub.add_parser("query"); s.add_argument("term"); s.add_argument("--days", type=int, default=30); s.add_argument("--limit", type=int, default=20); s.set_defaults(func=cmd_query)
    sub.add_parser("db").set_defaults(func=cmd_db)
    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
