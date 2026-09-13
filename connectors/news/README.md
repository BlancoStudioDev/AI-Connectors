# 📰 News — notizie del giorno + analisi con LLM

Tre script che lavorano insieme per portare le notizie all'agente e all'utente:

| Script | Cosa fa | Dipendenze |
|---|---|---|
| `news_report.py` | Report puro da **feed RSS italiani** (ANSA prima pagina/tech/scienza, Hacker News, The Verge): nessuna API key, solo `feedparser` + `requests` | stdlib + feedparser |
| `news_daily.py` | Cron del mattino (06:00): esegue `news_report.py`, impagina il risultato in un `.md` intitolato con il giorno e lo **invia su Telegram** come documento | requests |
| `news.py` | Skill completa: scarica le news di oggi, le **classifica con un LLM** (DeepSeek), le storicizza su **SQLite** (via repo [News-Evaluator](https://github.com/BlancoStudioDev) clonata in `~/News-Evaluator`) e offre digest/trend/query sullo storico | httpx, python-dotenv, aiosqlite, News-Evaluator |

## Comandi di `news.py`

```bash
python news.py today                      # news di oggi (RSS mondo + economia)
python news.py ingest [--days N|--date D] # classifica con LLM e salva nello storico
python news.py brief [--days N]           # digest LLM: mondo, economia, direzioni
python news.py trend "TERMINE" [--days N] # direzione di lungo periodo (Google News RSS)
python news.py query "testo" [--days N]   # ricerca nello storico classificato
python news.py db                         # statistiche dello storico
```

`news.py trend` interroga Google News RSS per il termine e calcola la direzione (volume/tempi) con l'LLM: utile per "come sta andando X negli ultimi giorni?".

## Configurazione — `.env`

```
DEEPSEEK_API_KEY=sk-...
DEEPSEEK_BASE_URL=https://api.deepseek.com/v1
DEEPSEEK_MODEL=deepseek-chat
```

⚠️ Serve anche la repo **News-Evaluator** clonata in `~/News-Evaluator` (contiene lo schema SQLite usato da `news.py` per lo storico).

## Cron consigliato

```cron
# Report del mattino alle 6:00 (Europe/Rome)
0 6 * * * ~/agent-scripts/.venv/bin/python ~/agent-scripts/news_daily.py >> ~/agent-scripts/news_daily.log 2>&1
```

## File

- `news.py` — skill completa (RSS + LLM + storico)
- `news_report.py` — report RSS senza chiavi
- `news_daily.py` — invio del report del mattino su Telegram
