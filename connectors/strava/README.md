# 🚴 Strava — attività e analisi allenamenti via API ufficiale

Legge profilo, statistiche e attività da Strava, fa analisi aggregate per il coaching (volume settimanale, frequenza, velocità) e registra allenamenti completati. **Sola lettura + creazione attività: niente modifiche o cancellazioni.**

## File

- `strava.py` — script principale
- `strava_login.py` — scambio code→token una tantum

## Dipendenze

Solo stdlib. Nessun pacchetto.

## Configurazione

**1)** Crea un'app su [strava.com/settings/api](https://www.strava.com/settings/api) (Authorization Callback Domain: `localhost`) e metti le credenziali in `.env`:

```ini
STRAVA_CLIENT_ID=12345
STRAVA_CLIENT_SECRET=abc123...
```

**2)** Autorizzazione una tantum: apri nel browser

```
https://www.strava.com/oauth/authorize?client_id=IL_TUO_CLIENT_ID&response_type=code&redirect_uri=http://localhost/exchange_token&approval_prompt=auto&scope=read,profile:read_all,activity:read_all,activity:write
```

approva, copia il `code=...` dall'URL di redirect e chiudi il cerchio:

```bash
strava_login.py abc123...   # → salva strava_tokens.json (600)
```

I token si rinnovano da soli (`refresh_token`).

## Uso

```bash
strava.py me                        # profilo atleta
strava.py stats                     # totali 4 settimane / YTD / sempre
strava.py list 10 --type Ride       # ultime 10 uscite in bici
strava.py show 1234567890           # dettaglio (velocità, cardio, watt)
strava.py analyze --days 90         # analisi per coaching/piani
strava.py add "Uscita collinari" --type Ride --date 2026-09-01 --time 08:30 --dur 120 --dist 62 --elev 740
```

## Note operative per l'agente

- Per analisi/piani: esegui prima `analyze` e `stats`, poi ragiona sui numeri
- Strava **non supporta** "allenamenti pianificati" via API: i piani restano testo dell'agente, le sessioni completate si registrano con `add`
