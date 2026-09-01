#!/usr/bin/env python3
"""Strava skill via the official API.
Usage:
  strava.py me                              -> athlete profile
  strava.py stats                           -> totals: last 4 weeks / YTD / all time
  strava.py list [N] [--type Ride]          -> last N activities (default 5)
  strava.py show <id>                       -> activity details (speed, HR, watts)
  strava.py analyze [--days 90] [--type Ride] -> aggregated analysis for coaching/plans
  strava.py add "Title" --type Ride --date YYYY-MM-DD --time HH:MM --dur MIN [--dist KM] [--elev M] [--desc T]
Tokens: strava_tokens.json (600) next to this script. One-time login with strava_login.py <code>
"""
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
TOKENS = HERE / 'strava_tokens.json'
API = 'https://www.strava.com/api/v3'


def load_cfg():
    cfg = {}
    env = HERE / '.env'
    if env.exists():
        for line in env.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                k, v = line.split('=', 1)
                cfg[k.strip()] = v.strip()
    return cfg


def save_tokens(t):
    json.dump(t, open(TOKENS, 'w'))
    os.chmod(TOKENS, 0o600)


def refresh(t):
    cfg = load_cfg()
    data = urllib.parse.urlencode({
        'client_id': cfg['STRAVA_CLIENT_ID'],
        'client_secret': cfg['STRAVA_CLIENT_SECRET'],
        'grant_type': 'refresh_token',
        'refresh_token': t['refresh_token'],
    }).encode()
    with urllib.request.urlopen(urllib.request.Request('https://www.strava.com/oauth/token', data=data), timeout=30) as r:
        n = json.load(r)
    t.update({'access_token': n['access_token'], 'refresh_token': n['refresh_token'], 'expires_at': n['expires_at']})
    save_tokens(t)
    return t


def get_token():
    t = json.load(open(TOKENS))
    if t.get('expires_at', 0) - 60 < time.time():
        t = refresh(t)
    return t['access_token']


def api(path, params=None):
    url = f'{API}{path}'
    if params:
        url += '?' + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={'Authorization': f'Bearer {get_token()}'})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def post(path, fields):
    data = urllib.parse.urlencode(fields).encode()
    req = urllib.request.Request(f'{API}{path}', data=data, headers={'Authorization': f'Bearer {get_token()}'})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def fmt_km(m):
    return f"{m / 1000:.1f}"


def fmt_hms(sec):
    sec = int(sec)
    return f"{sec // 3600}h{sec % 3600 // 60:02d}m" if sec >= 3600 else f"{sec // 60}m{sec % 60:02d}s"


def fmt_speed(a):
    return f"{a * 3.6:.1f} km/h" if a else "-"


def cmd_me(args):
    a = api('/athlete')
    print(f"🏃 {a.get('firstname')} {a.get('lastname')} — {a.get('city') or ''} {a.get('country') or ''}")
    print(f"   Weight: {a.get('weight') or '?'} kg | FTP: {a.get('ftp') or '?'} W | Premium: {bool(a.get('premium'))}")


def cmd_stats(args):
    me = api('/athlete')
    s = api(f"/athletes/{me['id']}/stats")
    for label, key in [('Last 4 weeks', 'recent_ride_totals'), ('Year to date', 'ytd_ride_totals'), ('All time', 'all_ride_totals')]:
        t = s.get(key, {})
        print(f"🚴 {label}: {fmt_km(t.get('distance', 0))} km | {t.get('count', 0)} rides | elevation {t.get('elevation_gain', 0):.0f} m | {fmt_hms(t.get('moving_time', 0))}")
    r = s.get('recent_run_totals', {})
    if r.get('count'):
        print(f"🏃 Last 4 weeks run: {fmt_km(r.get('distance', 0))} km | {r.get('count', 0)} runs")


def cmd_list(args):
    params = {'per_page': args.n}
    if args.type:
        params['type'] = args.type
    acts = api('/athlete/activities', params)
    if not acts:
        print("(no activities)")
    for a in acts:
        d = datetime.fromisoformat(a['start_date'].replace('Z', '+00:00')).astimezone(timezone.utc)
        print(f"[{a['id']}] {d:%a %d/%m %H:%M} | {a['name'][:45]} | {a['type']} | {fmt_km(a['distance'])} km | {fmt_hms(a['moving_time'])} | {fmt_speed(a.get('average_speed'))} | +{a.get('total_elevation_gain', 0):.0f} m")


def cmd_show(args):
    a = api(f'/activities/{args.id}')
    print(f"📌 {a['name']}")
    print(f"   {a['start_date_local']} | {a['type']} | {fmt_km(a['distance'])} km | {fmt_hms(a['moving_time'])} (total {fmt_hms(a['elapsed_time'])})")
    print(f"   Avg speed {fmt_speed(a.get('average_speed'))} | max {fmt_speed(a.get('max_speed'))} | elevation +{a.get('total_elevation_gain', 0):.0f} m")
    if a.get('average_heartrate'):
        print(f"   Heart rate: avg {a['average_heartrate']:.0f} bpm | max {a.get('max_heartrate') or '?'}")
    if a.get('average_watts'):
        print(f"   Power: avg {a['average_watts']:.0f} W" + (f" (NP {a['weighted_average_watts']:.0f})" if a.get('weighted_average_watts') else ''))
    if a.get('kilojoules'):
        print(f"   Energy: {a['kilojoules']:.0f} kJ | Calories: {a.get('calories', '?')}")
    if a.get('description'):
        print(f"   Notes: {a['description'][:200]}")


def cmd_analyze(args):
    params = {'per_page': 100}
    if args.type:
        params['type'] = args.type
    acts = api('/athlete/activities', params)
    cutoff = time.time() - args.days * 86400
    sel = [a for a in acts if datetime.fromisoformat(a['start_date'].replace('Z', '+00:00')).timestamp() >= cutoff]
    if not sel:
        print(f"No {args.type or ''} activities in the last {args.days} days.")
        return
    tot_km = sum(a['distance'] for a in sel) / 1000
    tot_elev = sum(a.get('total_elevation_gain', 0) for a in sel)
    tot_time = sum(a['moving_time'] for a in sel)
    speeds = [(a['average_speed'], a['moving_time']) for a in sel if a.get('average_speed')]
    avg_spd = sum(s * t for s, t in speeds) / sum(t for _, t in speeds) if speeds else 0
    best = max(sel, key=lambda a: a['distance'])
    weeks = {}
    for a in sel:
        d = datetime.fromisoformat(a['start_date'].replace('Z', '+00:00'))
        wk = d.strftime('%W')
        weeks.setdefault(wk, [0, 0, 0])
        weeks[wk][0] += a['distance'] / 1000
        weeks[wk][1] += 1
        weeks[wk][2] += a.get('total_elevation_gain', 0)
    tlabel = args.type or 'all'
    print(f"📊 STRAVA ANALYSIS — {tlabel}, last {args.days} days ({len(sel)} activities)")
    print(f"   Total: {tot_km:.1f} km | {tot_time / 3600:.1f} h | +{tot_elev:.0f} m | avg speed {avg_spd * 3.6:.1f} km/h")
    print(f"   Average per activity: {tot_km / len(sel):.1f} km | frequency {len(sel) / max(args.days / 7, 1):.1f}/week")
    print(f"   Best ride: {fmt_km(best['distance'])} km — '{best['name'][:40]}'")
    print("   Weeks (km, activities, elevation):")
    for wk in sorted(weeks)[-12:]:
        k, n, e = weeks[wk]
        print(f"     wk.{wk}: {k:6.1f} km | {n} rides | +{e:.0f} m")
    print("   Last 5:")
    for a in sorted(sel, key=lambda x: x['start_date'])[-5:]:
        d = datetime.fromisoformat(a['start_date'].replace('Z', '+00:00'))
        print(f"     {d:%d/%m} {a['name'][:35]} — {fmt_km(a['distance'])} km @ {fmt_speed(a.get('average_speed'))}")


def cmd_add(args):
    start_local = f"{args.date}T{args.time}:00"
    st = datetime.strptime(start_local, "%Y-%m-%dT%H:%M:%S")
    fields = {
        'name': args.title,
        'type': args.type,
        'start_date_local': start_local,
        'elapsed_time': args.dur * 60,
    }
    if args.dist:
        fields['distance'] = int(args.dist * 1000)
    if args.elev:
        fields['total_elevation_gain'] = args.elev
    if args.desc:
        fields['description'] = args.desc
    a = post('/activities', fields)
    print(f"✅ Activity created on Strava: '{a['name']}' {start_local} | {fmt_km(a.get('distance', 0))} km | {args.dur} min — https://www.strava.com/activities/{a['id']}")


def main():
    import argparse
    p = argparse.ArgumentParser(description='Strava skill')
    sp = p.add_subparsers(dest='cmd', required=True)
    sp.add_parser('me').set_defaults(fn=cmd_me)
    sp.add_parser('stats').set_defaults(fn=cmd_stats)
    l = sp.add_parser('list')
    l.add_argument('n', nargs='?', type=int, default=5)
    l.add_argument('--type')
    l.set_defaults(fn=cmd_list)
    s = sp.add_parser('show')
    s.add_argument('id')
    s.set_defaults(fn=cmd_show)
    a = sp.add_parser('analyze')
    a.add_argument('--days', type=int, default=90)
    a.add_argument('--type')
    a.set_defaults(fn=cmd_analyze)
    ad = sp.add_parser('add')
    ad.add_argument('title')
    ad.add_argument('--type', default='Ride')
    ad.add_argument('--date', required=True)
    ad.add_argument('--time', default='08:00')
    ad.add_argument('--dur', type=int, required=True)
    ad.add_argument('--dist', type=float)
    ad.add_argument('--elev', type=float)
    ad.add_argument('--desc')
    ad.set_defaults(fn=cmd_add)
    args = p.parse_args()
    args.fn(args)


if __name__ == '__main__':
    main()
