# 🥗 Nutrizione — log macro giornaliero con stima via LLM

Traccia calorie, macro e acqua su un log JSON locale, con target calcolati (Mifflin-St Jeor) per un percorso di bulk. L'agente stima le macro da descrizioni in linguaggio naturale: opzionalmente lo script chiama un LLM per la stima.

## File

- `nutri.py`

## Dipendenze

Solo stdlib. Lo stato vive in `data/nutri.json` e `data/nutri_profile.json` (creati allo primo avvio, permessi 600).

## Configurazione — `.env` (opzionale)

La stima automatica delle macro usa un LLM; senza chiave lo script usa una tabella di fallback per alimenti comuni:

```ini
ZAI_API_KEY=la-tua-api-key
ZAI_MODEL=glm-5.3-flash
```

## Uso

```bash
nutri.py status                       # bilancio di oggi vs target
nutri.py add "100g petto pollo + 80g riso"          # macro stimate via LLM
nutri.py add "shaker proteico" --pro 30 --kcal 120  # macro esplicite
nutri.py water 500                    # +500ml acqua
nutri.py history --days 7             # trend
nutri.py target                       # target calcolati (BMR/TDEE/macro)
nutri.py config --weight 80 --height 186 --age 21 --bf 11 --activity 1.55 --target-weight 85
nutri.py reset --today                # azzera oggi
```

## Note operative per l'agente

- Flusso ideale: l'utente manda "ho mangiato X" durante il giorno → l'agente fa `add` → a fine giornata `status` e suggerisce cosa integrare
- I target di default sono quelli del profilo (bulk +400 kcal sul TDEE, proteine 2,1 g/kg del peso obiettivo) — si personalizzano con `config`
- Nessun consiglio medico: solo conteggio numeri
