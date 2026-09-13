# 🎬 YouTube Shorts — pipeline video storici con approvazione via agente

Una pipeline completa che **genera, assembla e pubblica** YouTube Shorts storici (in italiano) sul canale dell'utente, con l'agente AI come *revision editor*: ogni mattina i video arrivano in chat su Telegram, l'utente li approva o scarta parlando con l'agente, e gli approvati escono negli orari programmati.

Il workflow è stato sviluppato per il canale **Cultura Antica** (shorts di storia antica), ma i temi cambiano ogni giorno e la struttura è riutilizzabile per qualsiasi nicchia.

## Come funziona (pipeline)

| Fase | Script | Cosa fa |
|---|---|---|
| 1. Script | `workflow/01_generate_script.py` | DeepSeek sceglie un tema storico **mai ripetuto** (stato in `data/state.json`) e produce: hook, narrazione divisa in 5-7 scene con parole chiave per le immagini, titolo YouTube, descrizione + hashtag |
| 2. Video | `workflow/02_make_video.py` | Montaggio con **ffmpeg**: voce TTS italiana (Microsoft Edge Neural, gratis, con timestamp parola-per-parola), immagini storiche reali da **Wikimedia Commons** (ricerca per parole chiave, scarto automatico delle immagini su sfondo bianco), effetto **Ken Burns** + dissolvenze incrociate, **sottotitoli sincronizzati** bianchi/oro con bordo nero (ASS), musica CC di sottofondo (Kevin MacLeod, attribuita in descrizione) |
| 3. Approvazione | `approve.py` | I video finiscono in chat Telegram; l'utente decide con l'agente |
| 4. Pubblicazione | `workflow/03_upload_youtube.py` | Upload via Playwright su YouTube Studio: titolo, descrizione + hashtag + attribuzioni, pubblico/non per bambini, orario programmato |

## Il flusso quotidiano

```
07:00  morning_run.sh      → genera 2 video (temi diversi) e li invia su Telegram
07:15  (utente + agente)   → "approva 1", "vanno bene entrambi", "scarta 2", "rigenera 1"
09:30  tick.sh             → promemoria se nulla è ancora stato approvato
10:00  publish_due.sh 1    → esce il 1° approvato (notifica Telegram col link)
14:00  publish_due.sh 2    → esce il 2° approvato
```

Tutti gli orari sono **Europe/Rome** a prova di ora legale (il `tick.sh` gira ogni 5 minuti dal cron e verifica l'ora romana), con lock anti-sovrapposizione e guardie anti-doppioni.

## Il connettore per l'agente: `approve.py`

```bash
# stato del giorno (per l'agente: cosa è approvato/scartato/in attesa)
python approve.py status
python approve.py 1 ok     # approva il video 1  → esce alle 10:00
python approve.py 2 ok     # approva il video 2  → esce alle 14:00
python approve.py 2 no     # scarta il video 2
```

L'agente interpreta il linguaggio naturale dell'utente ("approva il primo", "vanno bene entrambi", "il secondo no") e traduce in questi comandi. Il primo approvato esce alle 10:00, il secondo alle 14:00; se ne viene approvato uno solo esce solo quello.

### Rigenerare un video scartato

```bash
workflow/morning_run.sh regen 1   # nuovo tema + nuovo video per lo slot 1 (~5 min, riarriva in chat)
```

## File

- `approve.py` — connettore agente (solo stdlib)
- `workflow/01_generate_script.py` — generatore script (DeepSeek)
- `workflow/02_make_video.py` — motore video (TTS + Wikimedia + ffmpeg)
- `workflow/03_upload_youtube.py` — upload su YouTube Studio (Playwright)
- `workflow/morning_run.sh` — generazione mattutina + invio Telegram
- `workflow/publish_due.sh` — pubblicazione allo slot orario
- `workflow/tick.sh` — entrypoint cron (ogni 5 minuti)
- `workflow/run_workflow.sh` — modalità fully-automatic (salta l'approvazione)
- `workflow/send_video.py` — invio video su Telegram (Bot API, multipart)
- `workflow/notify.py` — notifiche testuali Telegram
- `workflow/config.example.json` — configurazione (⚠️ copiare in `config.json`, mai committato)
- `workflow/crontab.txt` — righe cron consigliate

## Dipendenze

- Python 3.10+ con `edge-tts`, `playwright` (`playwright install chromium`) nel venv
- **ffmpeg statico** (consigliato: build johnvansickle, con `subtitles`/`libass`, `xfade`, `zoompan`)
- **Xvfb** per i login Google headful (Google blocca i browser headless)
- Un bot Telegram (token + chat dell'utente) per invio video e notifiche
- API key DeepSeek (o adattare `01` a un altro LLM con output JSON)
- Font con grassetto (DejaVu Sans Bold su Ubuntu) per i sottotitoli

## Configurazione — `workflow/config.json`

```json
{
  "invideo_email": "", "invideo_password": "",      // sessione alternativa (opzionale)
  "youtube_email": "", "youtube_password": "",      // account del canale
  "deepseek_api_key": "", "deepseek_base_url": "https://api.deepseek.com/v1", "deepseek_model": "deepseek-chat",
  "canale_istruzione": "Cultura Antica"
}
```

⚠️ `config.json` contiene le **password degli account Google**: permission `600`, mai in git. Le sessioni browser (login Google già fatto) vivono in `sessions/{invideo,youtube}/` — anche quelle mai in git: al primo avvio Playwright apre il login Google e dopo l'eventuale 2FA la sessione resta salvata e persistente.

## Installazione

```bash
# 1. copia il workflow sul server (vedi install.sh nella root del repo)
# 2. venv: pip install edge-tts playwright && playwright install chromium
# 3. ffmpeg statico in ~/agent-scripts/bin
# 4. sudo apt install xvfb
# 5. cp config.example.json config.json (poi compila, chmod 600)
# 6. primo login YouTube (sessione persistente):
export DISPLAY=:99 && (Xvfb :99 &)
python 03_upload_youtube.py --outdir <dir_prova>        # fa il login la prima volta
# 7. cron (vedi crontab.txt)
```

## Stato e file dati (git-ignored)

- `data/morning.json` — video del giorno: slot, titolo, stato (`pending/approved/rejected/failed/published`), percorso
- `data/state.json` — temi già trattati (rotazione infinita, niente ripetizioni)
- `data/output/<TS>_slot<N>/` — `script.json`, immagini, `video.mp4`
- `data/imgcache/` — cache immagini Wikimedia (riduce le chiamate all'API)
- `sessions/` — profili browser Playwright persistenti

## Note

- Durata target ≤ 60s: se la voce supera il limite, il TTS riprova automaticamente a velocità maggiore (+16%, +25%)
- Le immagini vengono scaricate da Wikimedia Commons **con rate-limiting e User-Agent identificativo** (policy dell'API)
- Musica: tracce Kevin MacLeod (incompetech.com) CC BY 4.0 — l'attribuzione viene aggiunta automaticamente in descrizione, insieme al credito immagini Wikimedia
- In alternativa alla pipeline locale esiste un ramo **Invideo AI** (`02_invideo.py`, non incluso qui): automazione browser del loro Agent Two — richiede però crediti a pagamento per l'export completo
