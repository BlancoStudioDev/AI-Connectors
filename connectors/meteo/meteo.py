#!/usr/bin/env python3
"""Weather skill (Open-Meteo, free, no API key).
Usage:
  meteo.py now "Milan"                       -> current conditions
  meteo.py forecast "Milan" [--days 3]       -> daily forecast
  meteo.py hour "Genoa" [--hours 12]         -> hourly detail
  meteo.py bike "Genoa" [--hours 12]         -> hours suitable for a bike ride (✅/❌)
"""
import json
import sys
import urllib.parse
import urllib.request

UA = {'User-Agent': 'ai-connectors-meteo/1.0'}

WMO = {
    0: 'Clear sky', 1: 'Mostly clear', 2: 'Partly cloudy', 3: 'Overcast',
    45: 'Fog', 48: 'Rime fog', 51: 'Light drizzle', 53: 'Drizzle',
    55: 'Heavy drizzle', 56: 'Freezing drizzle', 57: 'Heavy freezing drizzle',
    61: 'Light rain', 63: 'Rain', 65: 'Heavy rain', 66: 'Freezing rain',
    67: 'Heavy freezing rain', 71: 'Light snow', 73: 'Snow', 75: 'Heavy snow',
    77: 'Snow grains', 80: 'Light showers', 81: 'Showers', 82: 'Violent showers',
    85: 'Snow showers', 86: 'Heavy snow showers', 95: 'Thunderstorm',
    96: 'Thunderstorm with hail', 99: 'Thunderstorm with heavy hail',
}


def http_json(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def geocode(name):
    # 1) Open-Meteo geocoding (cities/towns); 2) Nominatim fallback (even small localities)
    try:
        d = http_json('https://geocoding-api.open-meteo.com/v1/search?' + urllib.parse.urlencode(
            {'name': name, 'count': 1, 'language': 'en', 'format': 'json'}))
        if d.get('results'):
            r = d['results'][0]
            label = r.get('name', name) + (f", {r.get('admin1')}" if r.get('admin1') else '')
            return r['latitude'], r['longitude'], label
    except Exception:
        pass
    d = http_json('https://nominatim.openstreetmap.org/search?' + urllib.parse.urlencode(
        {'q': name, 'format': 'json', 'limit': 1}))
    if not d:
        sys.exit(f"Place not found: {name}")
    r = d[0]
    label = r.get('display_name', name).split(',')[0]
    return float(r['lat']), float(r['lon']), label


def wind_dir(deg):
    return ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW'][int((deg + 22.5) // 45) % 8]


def main():
    args = list(sys.argv[1:])
    cmd = args.pop(0) if args else 'forecast'
    hours, days = 12, 2
    while '--hours' in args:
        i = args.index('--hours')
        hours = int(args[i + 1])
        del args[i:i + 2]
    while '--days' in args:
        i = args.index('--days')
        days = int(args[i + 1])
        del args[i:i + 2]
    place = args[0].strip('"') if args else 'Milan'
    lat, lon, label = geocode(place)
    base = 'https://api.open-meteo.com/v1/forecast?' + urllib.parse.urlencode(
        {'latitude': lat, 'longitude': lon, 'timezone': 'auto'})

    if cmd == 'now':
        d = http_json(base + '&current=temperature_2m,apparent_temperature,precipitation,weather_code,wind_speed_10m,wind_direction_10m,wind_gusts_10m,relative_humidity_2m')
        c = d['current']
        print(f"🌤️ {label} — NOW ({c['time'][11:16]})")
        print(f"   {WMO.get(c['weather_code'], '?')} | {c['temperature_2m']}°C (feels like {c['apparent_temperature']}°C)")
        print(f"   Wind {c['wind_speed_10m']} km/h {wind_dir(c['wind_direction_10m'])} (gusts {c['wind_gusts_10m']}) | Humidity {c['relative_humidity_2m']}% | Rain {c['precipitation']} mm")
    elif cmd == 'forecast':
        d = http_json(base + f'&daily=weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max,precipitation_sum,wind_speed_10m_max&forecast_days={days}')
        print(f"📅 {label} — {days}-day forecast")
        for i, day in enumerate(d['daily']['time']):
            print(f"   {day}: {WMO.get(d['daily']['weather_code'][i], '?')} | {d['daily']['temperature_2m_min'][i]}-{d['daily']['temperature_2m_max'][i]}°C | rain {d['daily']['precipitation_probability_max'][i]}% ({d['daily']['precipitation_sum'][i]} mm) | max wind {d['daily']['wind_speed_10m_max'][i]} km/h")
    elif cmd in ('hour', 'bike'):
        d = http_json(base + f'&hourly=temperature_2m,precipitation_probability,precipitation,weather_code,wind_speed_10m,wind_gusts_10m&forecast_hours={hours}')
        h = d['hourly']
        print(f"🕐 {label} — next {hours} hours" + (' (bike index)' if cmd == 'bike' else ''))
        for i, t in enumerate(h['time']):
            mark = ''
            if cmd == 'bike':
                ok = h['precipitation_probability'][i] <= 30 and h['wind_speed_10m'][i] < 25 and 5 <= h['temperature_2m'][i] <= 30
                mark = '✅' if ok else '❌'
            print(f"   {mark}{t[11:16]} | {h['temperature_2m'][i]}°C | {WMO.get(h['weather_code'][i], '?')} | rain {h['precipitation_probability'][i]}% | wind {h['wind_speed_10m'][i]} km/h (gusts {h['wind_gusts_10m'][i]})")
    else:
        print('commands: now | forecast | hour | bike')


if __name__ == '__main__':
    main()
