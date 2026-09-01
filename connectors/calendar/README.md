# 📅 Calendar — calendario Apple iCloud via CalDAV

Legge, crea, modifica ed elimina eventi sul calendario Apple/iCloud direttamente via CalDAV, con fuso `Europe/Rome`.

## File

- `cal.py`

## Dipendenze

```bash
~/agent-scripts/.venv/bin/pip install caldav vobject
```

## Configurazione — `.env`

Serve una **password per app** Apple (appleid.apple.com → Accesso e sicurezza → Password specifiche per app), non la password dell'Apple ID:

```ini
APPLE_EMAIL=latuaemail@icloud.com
ICLOUD_APP_PASSWORD=xxxx-xxxx-xxxx-xxxx
```

## Uso

```bash
cal.py calendars                       # elenca i calendari disponibili
cal.py read [--cal Sport] [--days 7] [--from 2026-09-01] [--search dentista]
cal.py add "Dentista" --date 2026-09-02 --start 15:00 --dur 60 --cal Casa --loc "Via X 1"
cal.py add "Weekend lago" --date 2026-09-12          # evento tutto il giorno
cal.py edit a1b2c3 --start 16:00 --loc "Studio"      # per prefisso UID (vedi read)
cal.py delete a1b2c3
```

## Note operative per l'agente

- `read` mostra l'`[uid:primi8caratteri]` di ogni evento: è la chiave per `edit`/`delete`
- Gli eventi "tutto il giorno" si creano senza `--start`
- Lo script gestisce gli eventi ricorrenti via `expand=True` nelle ricerche
