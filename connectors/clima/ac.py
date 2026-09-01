#!/usr/bin/env python3
"""CLIMA skill — Hisense air conditioners (HiSmart Life app, Ayla EU cloud).

Real-world protocol (reverse-engineered from the official app traffic):
1. Login on user-field-eu.aylanetworks.com with the Hisense app_id/app_secret
2. Devices listed via ads-eu.aylanetworks.com/apiv1/devices.json
   (includes local IP, MAC, room temperature)
3. Commands are written to the packed bitmap property 't_control_value':
   fan [0:5], power [5:7], mode [8:12], target temp [16:23] — each field
   carries its own "changed" flag bit; the unit applies only flagged fields.
4. The tool verifies after each write and retries automatically.

Usage:
  ac.py list | status                        -> state of every AC
  ac.py get <name>                           -> details of one unit
  ac.py on <name|all> / off <name|all>
  ac.py temp <name> <degC>                   -> set target (powers on if off)
  ac.py mode <name> <cool|heat|dry|fan|auto>
  ac.py fan <name> <auto|lower|low|medium|high|higher>
  ac.py set <name> [--temp N] [--mode M] [--fan F]

Names are substrings of the device names shown by 'list'; 'all' selects everything.
Credentials: .env next to this script (HI_SMARTLIFE_USER, HI_SMARTLIFE_PASS).
"""
import base64
import json
import os
import sys
import time
import urllib.request
import urllib.error
import ssl
from pathlib import Path

ENVF = Path(__file__).resolve().parent / ".env"
if not ENVF.exists():
    ENVF = Path.home() / "agent-scripts" / ".env"

USER_SERVER = 'user-field-eu.aylanetworks.com'
DEV_SERVER = 'ads-eu.aylanetworks.com'
APP_ID = 'Hisense-mw-id'
APP_SECRET = 'Hisense-' + base64.b64encode(
    b'\xc0\xedK,\xff+X\xfa\xf6p\x87\xaa\xbcV\x88\xfbI\xb4\xcf\xad'
).decode().rstrip('=').replace('+', '-').replace('/', '_')
UA = 'Dalvik/2.1.0 (Linux; U; Android 9.0; SM-G850F Build/LRX22G)'

MODE = {'fan': 0, 'heat': 1, 'cool': 2, 'dry': 3, 'auto': 4}
MODE_NAME = {0: 'fan', 1: 'heat', 2: 'cool', 3: 'dry', 4: 'auto'}
FAN = {'auto': 0, 'lower': 5, 'low': 6, 'medium': 7, 'high': 8, 'higher': 9}
FAN_NAME = {0: 'auto', 5: 'lower', 6: 'low', 7: 'medium', 8: 'high', 9: 'higher'}

SSL_CTX = ssl.create_default_context()


def load_env():
    env = {}
    if ENVF.exists():
        for line in ENVF.read_text().splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    return env


def http(method, url, payload=None, headers=None, timeout=25):
    data = json.dumps(payload).encode() if payload is not None else None
    h = {'User-Agent': UA, 'Accept': 'application/json',
         'Content-Type': 'application/json'}
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, data=data, headers=h, method=method)
    with urllib.request.urlopen(req, timeout=timeout, context=SSL_CTX) as r:
        return json.loads(r.read().decode())


def login():
    env = load_env()
    email = env.get('HI_SMARTLIFE_USER')
    pwd = env.get('HI_SMARTLIFE_PASS')
    if not email or not pwd:
        sys.exit('missing credentials in .env (HI_SMARTLIFE_USER / HI_SMARTLIFE_PASS)')
    q = {'user': {'email': email, 'password': pwd,
                  'application': {'app_id': APP_ID, 'app_secret': APP_SECRET}}}
    try:
        r = http('POST', f'https://{USER_SERVER}/users/sign_in.json', q,
                 {'Authorization': 'none'})
    except urllib.error.HTTPError as e:
        sys.exit(f'login failed: {e.code} {e.read()[:200]}')
    return r['access_token']


def api(token):
    return {'Authorization': 'auth_token ' + token}


def devices(h):
    return [d['device'] for d in http('GET', f'https://{DEV_SERVER}/apiv1/devices.json', headers=h)]


def props(h, dsn):
    r = http('GET', f'https://{DEV_SERVER}/apiv1/dsns/{dsn}/properties.json', headers=h)
    return {p['property']['name']: p['property'].get('value') for p in r}


def send(h, dsn, prop, value):
    try:
        http('POST', f'https://{DEV_SERVER}/apiv1/dsns/{dsn}/properties/{prop}/datapoints.json',
             {'datapoint': {'value': value}}, headers=h)
        return True
    except urllib.error.HTTPError as e:
        print(f'  ! error {prop}={value}: HTTP {e.code}')
        return False


# ---- t_control_value bitmap (Hisense/Ayla protocol) ----

def cv_clear(control):
    return control & 2868817502

def cv_power(control):
    return (control >> 6) & 1

def cv_set_power(control, on):
    return (control & ~(3 << 5)) | (((int(on) << 1) | 1) << 5)

def cv_mode(control):
    return (control >> 9) & 7

def cv_set_mode(control, mode):
    return (control & ~(15 << 8)) | (((mode << 1) | 1) << 8)

def cv_fan(control):
    return (control >> 1) & 15

def cv_set_fan(control, fan):
    return (control & ~31) | ((fan << 1) | 1)

def cv_temp(control):
    return (control >> 17) & 63

def cv_set_temp(control, temp):
    return (control & ~(127 << 16)) | (((temp << 1) | 1) << 16)


def match(name, devs):
    name = name.lower()
    if name in ('all', '*'):
        return devs
    out = [d for d in devs if name in (d.get('product_name') or '').lower()]
    if not out:
        avail = ', '.join(d.get('product_name', '?') for d in devs)
        sys.exit(f'no AC found for "{name}". Available: {avail}')
    return out


def decode(p):
    cv = p.get('t_control_value')
    if isinstance(cv, int):
        return cv_power(cv), cv_mode(cv), cv_temp(cv), cv_fan(cv)
    pw = p.get('t_power') or 0
    return pw, p.get('t_work_mode') or 0, p.get('t_temp'), 0


def show(h, devs, cache=None):
    print(f'{"Name":<22}{"IP":<16}{"State":<7}{"Mode":<7}{"Target":<8}{"Fan":<9}{"Room"}')
    for d in devs:
        p = (cache or {}).get(d['dsn']) or props(h, d['dsn'])
        pw, mode, temp, fan = decode(p)
        amb = p.get('f_temp_in')
        amb = f'{amb}C' if amb is not None else '?'
        print(f"{d.get('product_name','?'):<22}{d.get('lan_ip') or '?':<16}"
              f"{'ON' if pw == 1 else 'off':<7}{MODE_NAME.get(mode, '?'):<7}"
              f"{(f'{temp}C' if pw == 1 and temp else '-'):<8}"
              f"{FAN_NAME.get(fan, '?'):<9}{amb}")


def ensure_on(h, d):
    p = props(h, d['dsn'])
    cv = p.get('t_control_value')
    pw = ((cv >> 6) & 1) if isinstance(cv, int) else (p.get('t_power') or 0)
    if pw != 1:
        send(h, d['dsn'], 't_power', 1)
        time.sleep(8)
        return True
    return False


def apply(h, d, fn, verify=None, retries=2):
    """Write t_control_value, then verify it was applied (with retries)."""
    for attempt in range(retries + 1):
        p = props(h, d['dsn'])
        cv = p.get('t_control_value')
        cv = cv if isinstance(cv, int) else 0
        wanted = fn(cv_clear(cv))
        ok = send(h, d['dsn'], 't_control_value', wanted)
        if ok and verify:
            time.sleep(5)
            now = props(h, d['dsn']).get('t_control_value')
            if isinstance(now, int) and verify(now):
                return True
            time.sleep(2)
        elif ok:
            return True
        if attempt < retries:
            time.sleep(3)
    print(f"  ! {d.get('product_name')}: command not applied "
          "(unit is locked: cut its power for 30s and retry)")
    return False


def main():
    args = sys.argv[1:]
    h = api(login())
    devs = devices(h)
    if not devs:
        sys.exit("no devices on the account")

    if not args or args[0] in ('list', 'status'):
        show(h, devs)
        return

    a0 = args[0].lower()

    if a0 == 'get' and len(args) > 1:
        for d in match(args[1], devs):
            p = props(h, d['dsn'])
            print(f"{d.get('product_name')}: dsn={d['dsn']} ip={d.get('lan_ip')} "
                  f"model={d.get('model')} state={d.get('connection_status')}")
            pw, mode, temp, fan = decode(p)
            print(f"  on={'yes' if pw == 1 else 'no'} mode={MODE_NAME.get(mode, '?')} "
                  f"target={temp}C fan={FAN_NAME.get(fan, '?')} "
                  f"room={p.get('f_temp_in')}C")
        return

    if a0 == 'set' and len(args) > 1:
        name = args[1]
        opts = {}
        i = 2
        while i < len(args):
            if args[i].startswith('--') and i + 1 < len(args):
                opts[args[i][2:]] = args[i + 1]
                i += 2
            else:
                i += 1
        for d in match(name, devs):
            ensure_on(h, d)

            def fn(cv, o=opts):
                if 'mode' in o:
                    cv = cv_set_mode(cv, MODE[o['mode'].lower()])
                if 'temp' in o:
                    cv = cv_set_temp(cv, int(float(o['temp'])))
                if 'fan' in o:
                    cv = cv_set_fan(cv, FAN[o['fan'].lower()])
                return cv
            verify = None
            if 'temp' in opts:
                t = int(float(opts['temp']))
                verify = lambda cv: cv_temp(cv) == t
            apply(h, d, fn, verify=verify)
        show(h, match(args[1], devs))
        return

    target, cmd = a0, (args[1].lower() if len(args) > 1 else '')
    sel = match(target, devs)

    if cmd in ('on', 'off'):
        on = 1 if cmd == 'on' else 0
        for d in sel:
            apply(h, d, lambda cv: cv_set_power(cv, on),
                  verify=(lambda cv: cv_power(cv) == on))
        show(h, sel)

    elif cmd == 'temp' and len(args) > 2:
        t = int(float(args[2]))
        for d in sel:
            ensure_on(h, d)

            def fn(cv, t=t):
                if cv_mode(cv) == 0:
                    cv = cv_set_mode(cv, MODE['cool'])
                return cv_set_temp(cv, t)
            apply(h, d, fn, verify=lambda cv: cv_temp(cv) == t)
        show(h, sel)

    elif cmd == 'mode' and len(args) > 2:
        m = args[2].lower()
        if m not in MODE:
            sys.exit('mode: ' + '|'.join(MODE))
        for d in sel:
            ensure_on(h, d)
            apply(h, d, lambda cv: cv_set_mode(cv, MODE[m]),
                  verify=lambda cv: cv_mode(cv) == MODE[m])
        show(h, sel)

    elif cmd == 'fan' and len(args) > 2:
        f = args[2].lower()
        if f not in FAN:
            sys.exit('fan: ' + '|'.join(FAN))
        for d in sel:
            ensure_on(h, d)
            apply(h, d, lambda cv: cv_set_fan(cv, FAN[f]),
                  verify=lambda cv: cv_fan(cv) == FAN[f])
        show(h, sel)

    else:
        print(__doc__)


if __name__ == '__main__':
    main()
