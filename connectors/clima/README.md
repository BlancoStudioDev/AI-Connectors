# ❄️ Clima — condizionatori Hisense via app HiSmart Life (cloud Ayla EU)

Accende, spegne e regola i condizionatori Hisense collegati all'app **HiSmart Life** (Tuya *white-label*? No: il cloud reale è **Ayla Networks EU**). Funziona ovunque (anche da VPS), non serve essere sulla rete di casa.

## Come funziona (il protocollo, in breve)

Scavallando il traffico dell'app ufficiale è emerso che:

1. Il login avviene su `user-field-eu.aylanetworks.com` con `app_id`/`app_secret` dell'app Hisense (valori pubblici nell'ecosistema Ayla)
2. I dispositivi si leggono via `ads-eu.aylanetworks.com/apiv1/devices.json` (include IP locale, MAC, temperatura ambiente)
3. I comandi partono scrivendo la bitmap **`t_control_value`**: campi bit per bit — ventola `[0:5]`, accensione `[5:7]`, modalità `[8:12]`, target `[16:23]` — dove ogni campo porta il proprio bit di "modifica"
4. L'unità applica un campo solo se il suo bit di modifica è impostato: il tool verifica e riprova automaticamente

## File

- `ac.py`

## Dipendenze

Solo stdlib.

## Configurazione — `.env`

Le credenziali dell'**app HiSmart Life** (email e password con cui accedi all'app):

```ini
HI_SMARTLIFE_USER=latuaemail@example.com
HI_SMARTLIFE_PASS=lapassword
```

## Uso

```bash
ac.py list                    # stato di tutti: acceso, mode, target, ventola, temperatura ambiente
ac.py get sala                # dettagli di un'unità
ac.py on sala | off tutti     # accensione/spegnimento
ac.py temp ragazzi 23         # target 23°C (accende se spento)
ac.py mode ragazzi cool       # cool|heat|dry|fan|auto
ac.py fan ragazzi auto        # auto|lower|low|medium|high|higher
ac.py set sala --temp 24 --mode cool --fan auto
```

I nomi accettati sono sottostringhe dei nomi dei dispositivi (es. `sala` → `Sala_2025`); `tutti` li seleziona tutti. **Fai `list` per vedere i tuoi dispositivi reali.**

## Note operative per l'agente

- `list` è la verità: mostra i dispositivi realmente presenti sull'account (non assumerne il numero!)
- `temp`/`mode`/`fan` accendono l'unità se spenta e aspettano l'avvio della scheda prima di inviare il setpoint
- Se dopo i retry automatici un setpoint non si applica, l'unità è in stato bloccato: **staccare la corrente 30 secondi** e riprovare
- Lo script gira ovunque (cloud API): VPS, Mac, server casalingo

## Diagnostica utile

- Login `403 Invalid app_id`: app_id errato per il tuo ecosistema (per Hisense EU è `Hisense-mw-id`)
- Dispositivo `Online` ma comandi ignorati: caso del bit di modifica — usa `set` che imposta un campo per volta con verifica
