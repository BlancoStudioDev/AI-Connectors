# 🌤️ Meteo — condizioni e previsioni via Open-Meteo

Meteo attuale, previsioni giornaliere, dettaglio orario e un calcolo delle ore buone per uscire in bici. **Gratuito, senza API key.**

## File

- `meteo.py`

## Dipendenze

Solo stdlib. Nessuna configurazione.

## Uso

```bash
meteo.py now "Milano"                    # condizioni attuali
meteo.py forecast "Milano" --days 5      # previsioni giornaliere
meteo.py hour "Genova Pegli" --hours 12  # dettaglio orario
meteo.py bike "Genova Pegli" --hours 12  # ore ✅ buone per la bici
```

## Criteri del comando `bike`

- probabilità di pioggia < 30%
- vento < 25 km/h
- temperatura tra 5 e 30 °C

## Note operative per l'agente

- Il geocoding gestisce anche frazioni/località (fallback Nominatim, limitato all'Italia)
- Combinabile con Strava e il calendario per suggerire quando uscire
