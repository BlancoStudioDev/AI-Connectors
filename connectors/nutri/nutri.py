#!/usr/bin/env python3
"""Nutrition skill — daily macro/water log with LLM-assisted estimation.
Usage:
  nutri.py status                          -> today's macros vs target
  nutri.py add "100g chicken breast + 80g rice" [--kcal 350 --pro 35 --carb 40 --fat 8] [--water 500]
  nutri.py water 500                        -> add water (ml)
  nutri.py history [--days 7]              -> history
  nutri.py target                          -> show computed target
  nutri.py config --weight 75 --height 180 --age 30 --bf 15 --activity 1.5 --target-weight 80
  nutri.py reset --today                   -> reset today
  nutri.py reset --all                     -> reset everything
Data: data/nutri.json + data/nutri_profile.json (next to this script)
"""
import argparse, json, os, sys, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

BASE = Path(__file__).resolve().parent / "data"
BASE.mkdir(parents=True, exist_ok=True)
LOG = BASE / "nutri.json"
PROFILE = BASE / "nutri_profile.json"
ENVF = Path(__file__).resolve().parent / ".env"
if not ENVF.exists():
    ENVF = Path.home() / "agent-scripts" / ".env"
TZ = ZoneInfo(os.environ.get("NUTRI_TZ", "Europe/Rome"))

DEFAULT_PROFILE = {
    "weight": 75, "height": 180, "age": 30, "bf": 15,
    "activity": 1.5, "target_weight": 80,
    "goal": "lean bulk +0.5kg/month"
}

def load_profile():
    if PROFILE.exists():
        try:
            p = json.loads(PROFILE.read_text())
            return {**DEFAULT_PROFILE, **p}
        except: pass
    return DEFAULT_PROFILE.copy()

def save_profile(p):
    PROFILE.write_text(json.dumps(p, indent=2))
    os.chmod(PROFILE, 0o600)

def calc_targets(p):
    # Mifflin-St Jeor
    w, h, a = p["weight"], p["height"], p["age"]
    bmr = 10*w + 6.25*h - 5*a + 5
    tdee = bmr * p["activity"]
    # lean bulk +350-500
    target_kcal = int(round(tdee + 400))
    # protein 2.1g/kg of target weight
    pro = int(round(p["target_weight"] * 2.1))
    # fat 1.0g/kg
    fat = int(round(p["target_weight"] * 0.95))
    # carbs: remainder
    carb = int(round((target_kcal - pro*4 - fat*9)/4))
    water = int(round(p["weight"]*35 + 500))  # 35ml/kg + training
    return {"bmr": int(bmr), "tdee": int(tdee), "kcal": target_kcal, "pro": pro, "carb": carb, "fat": fat, "water": water}

def load_log():
    if LOG.exists():
        try: return json.loads(LOG.read_text())
        except: return {}
    return {}

def save_log(d):
    LOG.write_text(json.dumps(d, indent=2))
    os.chmod(LOG, 0o600)

def today_str():
    return datetime.datetime.now(TZ).date().isoformat()

def ensure_today(log):
    t = today_str()
    if t not in log:
        log[t] = {"entries": [], "water": 0, "tot": {"kcal":0,"pro":0,"carb":0,"fat":0}}
    return t

def estimate_macros_via_llm(desc):
    # Fallback LLM estimation if no explicit macros — best effort
    try:
        import os, json as js, urllib.request
        env = {}
        for line in ENVF.read_text().splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k,v=line.split("=",1); env[k.strip()]=v.strip()
        import urllib.request, json
        payload = json.dumps({
            "model": env.get("ZAI_MODEL","glm-5.3-flash"),
            "messages": [
                {"role":"system","content": "You are a nutritionist. Estimate kcal, protein g, carbs g, fat g for the food description. Reply with ONLY JSON {\"kcal\":int,\"pro\":float,\"carb\":float,\"fat\":float,\"water\":int,\"note\":str} and nothing else. Use standard portions if grams are missing."},
                {"role":"user","content": desc}
            ],
            "temperature": 0.2
        }).encode()
        req = urllib.request.Request("https://api.z.ai/api/paas/v4/chat/completions", data=payload, headers={"Content-Type":"application/json","Authorization":f"Bearer {env.get('ZAI_API_KEY')}"})
        with urllib.request.urlopen(req, timeout=20) as r:
            j=json.loads(r.read().decode())
            content=j["choices"][0]["message"]["content"]
            # extract JSON
            import re
            m=re.search(r"\{.*\}", content, re.S)
            if m:
                return json.loads(m.group(0))
    except Exception as e:
        pass
    return None

# --- small fallback table for common foods ---
FALLBACK = {
    "100g chicken breast": {"kcal":165,"pro":31,"carb":0,"fat":3.6},
    "100g cooked white rice": {"kcal":130,"pro":2.4,"carb":28,"fat":0.3},
    "80g raw rice": {"kcal":280,"pro":5,"carb":62,"fat":0.6},
    "2 eggs": {"kcal":140,"pro":12,"carb":1,"fat":10},
    "50g bread": {"kcal":130,"pro":4,"carb":25,"fat":1},
    "200ml milk": {"kcal":90,"pro":6,"carb":10,"fat":3},
}

def main():
    p = argparse.ArgumentParser(description="Nutrition tracker")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("status")
    a = sub.add_parser("add")
    a.add_argument("desc", nargs="?", default="")
    a.add_argument("--kcal", type=float)
    a.add_argument("--pro", type=float)
    a.add_argument("--carb", type=float)
    a.add_argument("--fat", type=float)
    a.add_argument("--water", type=int, default=0)
    a.add_argument("--note", default="")
    w = sub.add_parser("water")
    w.add_argument("ml", type=int)
    h = sub.add_parser("history")
    h.add_argument("--days", type=int, default=7)
    sub.add_parser("target")
    c = sub.add_parser("config")
    c.add_argument("--weight", type=float)
    c.add_argument("--height", type=float)
    c.add_argument("--age", type=int)
    c.add_argument("--bf", type=float)
    c.add_argument("--activity", type=float)
    c.add_argument("--target-weight", type=float, dest="target_weight")
    r = sub.add_parser("reset")
    r.add_argument("--today", action="store_true")
    r.add_argument("--all", action="store_true")
    args = p.parse_args()

    profile = load_profile()
    targets = calc_targets(profile)
    log = load_log()
    t = ensure_today(log)

    if args.cmd == "config":
        for k in ["weight","height","age","bf","activity","target_weight"]:
            v=getattr(args,k,None)
            if v is not None:
                profile[k]=v
        save_profile(profile)
        targets=calc_targets(profile)
        print(f"✅ Profile updated: {profile['weight']}kg, {profile['height']}cm, {profile['age']}y, BF {profile['bf']}%, target {profile['target_weight']}kg")
        print(f"Target: {targets['kcal']} kcal | P {targets['pro']}g C {targets['carb']}g F {targets['fat']}g | water {targets['water']}ml/day")
        print(f"BMR {targets['bmr']} TDEE {targets['tdee']} +400 bulk")
        return
    if args.cmd == "target":
        print(f"Profile: {profile['weight']}kg → {profile['target_weight']}kg, {profile['height']}cm, {profile['age']}y, BF {profile['bf']}%")
        print(f"BMR {targets['bmr']} | TDEE {targets['tdee']} (x{profile['activity']}) | Bulk target +400")
        print(f"→ {targets['kcal']} kcal | Pro {targets['pro']}g ({round(targets['pro']*4/targets['kcal']*100)}%) | Carb {targets['carb']}g | Fat {targets['fat']}g | Water {targets['water']}ml")
        print(f"Goal: {profile['goal']} — adjust with 'config'")
        return
    if args.cmd == "reset":
        if args.all:
            log={}
            save_log(log)
            print("🗑️ Nutrition log wiped")
        elif args.today:
            log[t]={"entries":[],"water":0,"tot":{"kcal":0,"pro":0,"carb":0,"fat":0}}
            save_log(log)
            print(f"🗑️ Today ({t}) reset")
        else:
            print("use --today or --all")
        return
    if args.cmd == "water":
        log[t]["water"]+=args.ml
        save_log(log)
        rem = targets["water"]-log[t]["water"]
        print(f"💧 +{args.ml}ml → today {log[t]['water']}ml / {targets['water']}ml ({'done' if rem<=0 else f'{rem}ml to go'})")
        return
    if args.cmd == "history":
        days=args.days
        print(f"📊 Last {days} days:")
        for i in range(days):
            d=(datetime.datetime.now(TZ).date()-datetime.timedelta(days=i)).isoformat()
            e=log.get(d)
            if not e: continue
            tot=e.get("tot",{})
            w=e.get("water",0)
            print(f" {d}: {tot.get('kcal',0)} kcal P{tot.get('pro',0)}g C{tot.get('carb',0)}g F{tot.get('fat',0)}g | water {w}ml | {len(e.get('entries',[]))} meals")
            for en in e.get("entries",[])[-3:]:
                print(f"   - {en['desc'][:60]} → {en['kcal']}kcal")
        return
    if args.cmd == "status":
        tot=log[t]["tot"]
        w=log[t]["water"]
        print(f"📅 Today {t} — {profile['weight']}kg → {profile['target_weight']}kg")
        print(f"Target: {targets['kcal']} kcal | P{targets['pro']} C{targets['carb']} F{targets['fat']} | 💧 {targets['water']}ml")
        print(f"Now: {tot['kcal']} kcal | P{tot['pro']}g C{tot['carb']}g F{tot['fat']}g | 💧 {w}ml")
        for k in ["kcal","pro","carb","fat"]:
            need=targets[k]-tot[k]
            pct=int(tot[k]/targets[k]*100) if targets[k] else 0
            unit = "g" if k != "kcal" else "kcal"
            status = "✅" if need<=0 else f"{need}{unit} to go"
            print(f"  {k}: {tot[k]}/{targets[k]} {pct}% → {status}")
        remaining = targets["water"] - w
        w_status = "✅" if w >= targets["water"] else f"{remaining}ml to go"
        print(f"  water: {w}/{targets['water']} {w_status}")
        # quick tips
        if tot["kcal"]<targets["kcal"]*0.6:
            print("💡 Under 60% kcal — add a ~400kcal snack (e.g. 80g rice + 100g chicken + olive oil)")
        if tot["pro"]<targets["pro"]*0.7:
            print(f"💡 Low protein — add {targets['pro']-tot['pro']}g (e.g. 30g shake + greek yogurt)")
        if w<1500:
            print("💧 Drink more water")
        if not log[t]["entries"]:
            print("ℹ️ No meals yet — use: nutri.py add \"what you ate\"")
        return
    if args.cmd == "add":
        desc=args.desc.strip()
        if not desc:
            print("usage: nutri.py add \"description\" [--kcal --pro --carb --fat] [--water ml]")
            return
        # explicit macros if given, otherwise estimate
        if args.kcal is not None:
            est={"kcal":args.kcal,"pro":args.pro or 0,"carb":args.carb or 0,"fat":args.fat or 0,"water":args.water}
        else:
            # try fallback table
            key=desc.lower().strip()
            if key in FALLBACK:
                est=FALLBACK[key]
                est["water"]=args.water
            else:
                est=estimate_macros_via_llm(desc)
                if not est:
                    print("⚠️ Can't estimate — add manual macros: --kcal 300 --pro 20 --carb 30 --fat 10")
                    print("Example: nutri.py add \"ham sandwich\" --kcal 350 --pro 18 --carb 45 --fat 12")
                    return
                est["water"]=args.water
                if "kcal" not in est: est["kcal"]=0
        entry={"ts":datetime.datetime.now(TZ).isoformat(),"desc":desc,"kcal":int(est.get("kcal",0)),"pro":int(est.get("pro",0)),"carb":int(est.get("carb",0)),"fat":int(est.get("fat",0)),"water":int(est.get("water",0)),"note":args.note}
        log[t]["entries"].append(entry)
        log[t]["tot"]["kcal"]+=entry["kcal"]
        log[t]["tot"]["pro"]+=entry["pro"]
        log[t]["tot"]["carb"]+=entry["carb"]
        log[t]["tot"]["fat"]+=entry["fat"]
        log[t]["water"]+=entry["water"]
        save_log(log)
        tot=log[t]["tot"]
        print(f"✅ Added: {desc} → {entry['kcal']}kcal P{entry['pro']} C{entry['carb']} F{entry['fat']} +{entry['water']}ml water")
        print(f"Today: {tot['kcal']}/{targets['kcal']} kcal | P{tot['pro']}/{targets['pro']}g | 💧 {log[t]['water']}/{targets['water']}ml")
        for k in ["kcal","pro"]:
            need=targets[k]-tot[k]
            if need>0:
                print(f"  {need}{'kcal' if k=='kcal' else 'g '+k} to go")
        return

if __name__ == "__main__": main()
