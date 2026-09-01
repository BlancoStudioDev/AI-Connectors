#!/usr/bin/env python3
"""Apple calendar (iCloud) skill via CalDAV.

Usage:
  cal.py calendars                          -> list calendars
  cal.py read [--cal NAME] [--days N] [--from YYYY-MM-DD] [--search TEXT]
                                            -> events (default: all cals, 7 days)
  cal.py add "Title" --date YYYY-MM-DD [--start HH:MM] [--end HH:MM]
                     [--dur MIN] [--cal NAME] [--loc "Place"] [--desc "Notes"]
  cal.py edit <UID or prefix> [--title T] [--date YYYY-MM-DD] [--start HH:MM]
                     [--end HH:MM] [--dur MIN] [--cal NAME] [--loc L] [--desc D]
  cal.py delete <UID or prefix> [--cal NAME]
"""
import argparse, os, sys, datetime, logging


class _NoCaldavSpam(logging.Filter):
    def filter(self, record):
        return "modified to avoid compatibility" not in record.getMessage()


logging.getLogger().addFilter(_NoCaldavSpam())
from pathlib import Path
from zoneinfo import ZoneInfo
from caldav import DAVClient

ENV_PATH = Path(__file__).resolve().parent / ".env"
if not ENV_PATH.exists():
    ENV_PATH = Path.home() / "agent-scripts" / ".env"
CALDAV_URL = "https://caldav.icloud.com"


def load_env():
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


def get_client():
    load_env()
    user = os.environ.get("ICLOUD_USER") or os.environ.get("APPLE_EMAIL")
    pwd = os.environ.get("ICLOUD_APP_PASSWORD") or os.environ.get("APPLE_PASSWORD")
    if not user or not pwd:
        sys.exit("Missing credentials: need APPLE_EMAIL and ICLOUD_APP_PASSWORD in the .env file")
    return DAVClient(url=CALDAV_URL, username=user, password=pwd)


def get_calendars(client, name=None):
    cals = client.principal().calendars()
    if not cals:
        sys.exit("No calendars found on the account.")
    if name:
        for c in cals:
            if c.name == name:
                return [c]
        sys.exit(f"Calendar '{name}' not found. Available: " +
                 ", ".join(str(c.name) for c in cals))
    return cals


def local_tz():
    return ZoneInfo(os.environ.get("CAL_TZ", "Europe/Rome"))


def vget(vevent, name, default=None):
    """Safe access to vobject properties (avoids KeyError on missing props)."""
    try:
        return vevent.contents[name][0].value
    except (KeyError, IndexError, AttributeError, TypeError):
        return default


def fmt(vevent):
    title = str(vget(vevent, "summary") or "(untitled)")
    loc = str(vget(vevent, "location") or "")
    ds = vget(vevent, "dtstart")
    if ds is None:
        return ("?", title, loc, str(vget(vevent, "uid") or "?"))
    if isinstance(ds, datetime.datetime):
        when = ds.astimezone(local_tz()).strftime("%a %d %b %Y %H:%M")
        de = vget(vevent, "dtend")
        if de and isinstance(de, datetime.datetime):
            when += de.astimezone(local_tz()).strftime("-%H:%M")
    else:
        de = vget(vevent, "dtend") or ds
        when = f"{ds:%a %d %b %Y} -> {de:%a %d %b %Y} (all day)"
    uid = str(vget(vevent, "uid") or "?")
    return when, title, loc, uid


def find_event(client, uid_prefix, cal_name=None):
    """Find events by UID prefix (in all calendars or one)."""
    matches = []
    for cal in get_calendars(client, cal_name):
        try:
            events = cal.events()
        except Exception:
            continue
        for e in events:
            try:
                v = e.vobject_instance.vevent
                if str(v.uid.value).startswith(uid_prefix):
                    matches.append((cal, e))
            except Exception:
                continue
    return matches


def cmd_calendars(args):
    with get_client() as client:
        for c in get_calendars(client):
            try:
                n = len(c.events())
            except Exception:
                n = "?"
            print(f"- {c.name} ({n} events)")


def cmd_read(args):
    tz = local_tz()
    start = (datetime.datetime.strptime(args.from_, "%Y-%m-%d").date()
             if args.from_ else datetime.datetime.now(tz).date())
    start = datetime.datetime.combine(start, datetime.time(0, 0), tz)
    end = start + datetime.timedelta(days=args.days)
    rows = []
    with get_client() as client:
        for cal in get_calendars(client, args.cal):
            try:
                events = cal.search(start=start, end=end, event=True, expand=True)
            except Exception as ex:
                print(f"! {cal.name}: {ex}", file=sys.stderr)
                continue
            for e in events:
                v = e.vobject_instance.vevent
                when, title, loc, uid = fmt(v)
                if args.search and args.search.lower() not in (title + " " + loc).lower():
                    continue
                ds = vget(v, "dtstart")
                key = ds.astimezone(local_tz()).isoformat() if isinstance(ds, datetime.datetime) else (ds.isoformat() if ds else "")
                rows.append((key, when, title, loc, uid, cal.name))
    rows.sort(key=lambda r: r[0])
    print(f"Events {start:%d/%m/%Y} - {end:%d/%m/%Y} ({len(rows)} found):")
    for key, when, title, loc, uid, cname in rows:
        line = f"  {when}  |  {title}"
        if loc:
            line += f"  @{loc}"
        line += f"  [uid:{uid[:8]}] ({cname})"
        print(line)


def cmd_add(args):
    tz = local_tz()
    d = datetime.datetime.strptime(args.date, "%Y-%m-%d").date()
    if args.start:
        s = datetime.datetime.combine(d, datetime.time.fromisoformat(args.start), tz)
        if args.end:
            e = datetime.datetime.combine(d, datetime.time.fromisoformat(args.end), tz)
            if e <= s:
                e += datetime.timedelta(days=1)
        else:
            e = s + datetime.timedelta(minutes=args.dur)
        kw = {"dtstart": s, "dtend": e}
    else:
        kw = {"dtstart": d, "dtend": d + datetime.timedelta(days=1)}
    kw["summary"] = args.title
    if args.loc:
        kw["location"] = args.loc
    if args.desc:
        kw["description"] = args.desc
    with get_client() as client:
        cal = get_calendars(client, args.cal)[0]
        ev = cal.save_event(**kw)
        v = ev.vobject_instance.vevent
        print(f"Created in '{cal.name}': '{args.title}' (uid:{str(v.uid.value)[:8]})")


def cmd_edit(args):
    tz = local_tz()
    with get_client() as client:
        matches = find_event(client, args.uid, args.cal)
        if not matches:
            sys.exit(f"No event with uid starting with '{args.uid}'.")
        if len(matches) > 1:
            sys.exit(f"Ambiguous prefix ({len(matches)} events): use more characters.")
        cal, ev = matches[0]
        v = ev.vobject_instance.vevent
        old_when, old_title, _, _ = fmt(v)
        changes = []

        if args.title:
            if "summary" not in v.contents:
                v.add("summary")
            v.summary.value = args.title
            changes.append(f"title='{args.title}'")
        if args.loc is not None:
            if args.loc == "":
                if "location" in v.contents:
                    v.remove(v.location)
                changes.append("location removed")
            else:
                if "location" not in v.contents:
                    v.add("location")
                v.location.value = args.loc
                changes.append(f"location='{args.loc}'")
        if args.desc is not None:
            if args.desc == "":
                if "description" in v.contents:
                    v.remove(v.description)
                changes.append("notes removed")
            else:
                if "description" not in v.contents:
                    v.add("description")
                v.description.value = args.desc
                changes.append(f"notes='{args.desc}'")

        # date/time changes
        if args.date or args.start or args.end or args.dur is not None:
            ds = vget(v, "dtstart")
            if ds is None:
                sys.exit("Event without a start date: not editable.")
            allday = not isinstance(ds, datetime.datetime)
            if allday:
                cur_s = datetime.datetime.combine(ds, datetime.time(0, 0))
                de = vget(v, "dtend") or (ds + datetime.timedelta(days=1))
                cur_e = datetime.datetime.combine(de, datetime.time(0, 0))
            else:
                cur_s = ds.astimezone(tz)
                de = vget(v, "dtend")
                cur_e = de.astimezone(tz) if de else cur_s + datetime.timedelta(hours=1)
            dur = cur_e - cur_s

            new_date = (datetime.datetime.strptime(args.date, "%Y-%m-%d").date()
                        if args.date else cur_s.date())
            if args.start or args.end or args.dur is not None or not allday:
                start_t = (datetime.time.fromisoformat(args.start) if args.start
                           else (cur_s.time() if not allday else datetime.time(9, 0)))
                new_s = datetime.datetime.combine(new_date, start_t, tz)
                if args.end:
                    new_e = datetime.datetime.combine(new_s.date(), datetime.time.fromisoformat(args.end), tz)
                    if new_e <= new_s:
                        new_e += datetime.timedelta(days=1)
                elif args.dur is not None:
                    new_e = new_s + datetime.timedelta(minutes=args.dur)
                else:
                    new_e = new_s + dur
                v.dtstart.value = new_s
                if "dtend" in v.contents:
                    v.dtend.value = new_e
                else:
                    v.add("dtend").value = new_e
                changes.append(f"when->{new_s:%a %d %b %Y %H:%M}-{new_e:%H:%M}")
            elif args.date:
                ndur = ((vget(v, "dtend") or (ds + datetime.timedelta(days=1))) - ds)
                v.dtstart.value = new_date
                if "dtend" in v.contents:
                    v.dtend.value = new_date + ndur
                changes.append(f"when->{new_date:%a %d %b %Y} (all day)")

        if not changes:
            sys.exit("No changes specified (--title/--date/--start/--end/--loc/--desc).")
        ev.save()
        print(f"Modified '{old_title}' ({old_when}) in '{cal.name}':")
        for c in changes:
            print(f"  - {c}")
        now_when, now_title, _, uid = fmt(v)
        print(f"  Now: {now_when} | {now_title} [uid:{uid[:8]}]")


def cmd_delete(args):
    with get_client() as client:
        matches = find_event(client, args.uid, args.cal)
        if not matches:
            sys.exit(f"No event with uid starting with '{args.uid}'.")
        if len(matches) > 1:
            sys.exit(f"Ambiguous prefix ({len(matches)} events): use more characters.")
        cal, ev = matches[0]
        v = ev.vobject_instance.vevent
        when, title, _, _ = fmt(v)
        ev.delete()
        print(f"Deleted from '{cal.name}': {when} | {title}")


def main():
    p = argparse.ArgumentParser(description="Apple iCloud calendar skill")
    sp = p.add_subparsers(dest="cmd", required=True)
    sp.add_parser("calendars").set_defaults(fn=cmd_calendars)
    r = sp.add_parser("read")
    r.add_argument("--cal"); r.add_argument("--days", type=int, default=7)
    r.add_argument("--from", dest="from_"); r.add_argument("--search")
    r.set_defaults(fn=cmd_read)
    a = sp.add_parser("add"); a.add_argument("title"); a.add_argument("--date", required=True)
    a.add_argument("--start"); a.add_argument("--end"); a.add_argument("--dur", type=int, default=60)
    a.add_argument("--cal"); a.add_argument("--loc"); a.add_argument("--desc")
    a.set_defaults(fn=cmd_add)
    e = sp.add_parser("edit"); e.add_argument("uid")
    e.add_argument("--title"); e.add_argument("--date"); e.add_argument("--start")
    e.add_argument("--end"); e.add_argument("--dur", type=int)
    e.add_argument("--cal"); e.add_argument("--loc"); e.add_argument("--desc")
    e.set_defaults(fn=cmd_edit)
    d = sp.add_parser("delete"); d.add_argument("uid"); d.add_argument("--cal")
    d.set_defaults(fn=cmd_delete)
    args = p.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
