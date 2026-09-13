# 📺 Will Media — download automatico de "The Essential"

Scarica l'ultimo episodio de **"The Essential"** del canale YouTube di Will Media e lo invia in chat Telegram, ogni giorno via cron.

**Zero API ufficiali Google**: il rilevamento del nuovo video avviene via **RSS ufficiale del canale** (`youtube.com/feeds/videos.xml`, istantaneo e inaffidabile-proof), il download via **yt-dlp** (scraping).

## Logica di invio

- il video ≤ 48 MB → **Bot API** (`sendVideo`, streaming immediato in chat)
- il video > 48 MB → **Telethon** con l'account reale (sessione già autenticata) verso la chat del bot

## Uso

```bash
python essential.py            # controlla e invia se c'è un nuovo episodio
python essential.py --force    # scarica e reinvia anche se già inviato (test/risend)
python essential.py --status   # mostra l'ultimo inviato (stato in data/essential_state.json)
```

Il cron orario installa da solo la versione aggiornata di yt-dlp prima di girare (YouTube cambia spesso), vedi `crontab` sotto.

## Configurazione

Niente chiavi API YouTube. Servono:

- **Bot token + chat**: `~/telegram-agent/.env` (`BOT_TOKEN=...`) e `~/telegram-agent/admin.json` (già pronti se usi il bot dell'agente)
- **Telethon** (solo per file grandi): `TG_API_ID`, `TG_API_HASH` in `~/agent-scripts/.env` e la sessione `tg_session` già autenticata (`python telegram.py login` una volta)
- **yt-dlp** nel venv: `pip install yt-dlp`
- Il canale è configurato per costante (`CHANNEL_RSS`, `MARKER = "The Essential"`): per un altro canale basta cambiare `channel_id` e il marker del titolo in testa allo script

## Cron consigliato

```cron
# yt-dlp aggiornato ogni ora + controllo nuovo Essential
7 * * * * ~/agent-scripts/.venv/bin/pip install -qU yt-dlp && ~/agent-scripts/.venv/bin/python ~/agent-scripts/essential.py >> ~/agent-scripts/data/essential.log 2>&1
```

## File

- `essential.py` — tutto qui: RSS → yt-dlp → Telegram (Bot API o Telethon), con stato anti-duplicati
