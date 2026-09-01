#!/usr/bin/env python3
"""Telegram skill (real user account via Telethon): login, chats, read, send.
The session is stored in tg_session.session (permission 600) next to this script.
"""
import sys, os, argparse, asyncio
from pathlib import Path

BASE = Path(__file__).parent

def load_env():
    env = dict(os.environ)
    f = BASE / '.env'
    if not f.exists():
        f = Path.home() / 'agent-scripts' / '.env'
    if f.exists():
        for line in f.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                k, v = line.split('=', 1)
                env.setdefault(k.strip(), v.strip())
    return env

ENV = load_env()
API_ID = int(ENV['TG_API_ID'])
API_HASH = ENV['TG_API_HASH']
PHONE = ENV['TG_PHONE']
SESSION = str(BASE / 'tg_session')

from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError

def client():
    return TelegramClient(SESSION, API_ID, API_HASH)

def fmt(dt):
    try:
        return dt.astimezone().strftime('%d/%m %H:%M')
    except Exception:
        return str(dt)

async def login(args):
    c = client()
    await c.connect()
    try:
        if await c.is_user_authorized():
            me = await c.get_me()
            print(f"Already authenticated OK {me.first_name} (@{me.username or '-'}) id={me.id}")
            return
        if not args.code:
            sent = await c.send_code_request(PHONE)
            (BASE / 'tg_code_hash.txt').write_text(sent.phone_code_hash)
            print(f"Code sent to {PHONE}. Check the Telegram app or SMS.")
            print("Run again: telegram.py login --code <CODE>")
            return
        ph = BASE / 'tg_code_hash.txt'
        code_hash = ph.read_text().strip() if ph.exists() else None
        try:
            await c.sign_in(phone=PHONE, code=args.code, phone_code_hash=code_hash)
        except SessionPasswordNeededError:
            if not args.password:
                print("Account protected by 2FA: run again with --password 'PASSWORD'")
                return
            await c.sign_in(password=args.password)
        me = await c.get_me()
        print(f"Login OK {me.first_name} (@{me.username or '-'}) id={me.id}")
    finally:
        await c.disconnect()

async def chats(args):
    c = client()
    await c.connect()
    try:
        ds = await c.get_dialogs(limit=args.limit)
        for d in ds:
            tag = ' [channel]' if d.is_channel and not d.is_group else (' [group]' if d.is_group else '')
            unread = f"  <UNREAD:{d.unread_count}>" if d.unread_count else ''
            print(f"{d.id} | {d.name}{tag}{unread}")
    finally:
        await c.disconnect()

async def find_chat(c, query):
    q = query.lower().strip().lstrip('@')
    best = None
    async for d in c.iter_dialogs():
        name = (d.name or '').lower()
        if name == q:
            return d.entity
        if q in name and best is None:
            best = d.entity
    if best:
        return best
    return await c.get_entity(query)

async def read(args):
    c = client()
    await c.connect()
    try:
        ent = await find_chat(c, args.chat)
        if not ent:
            print(f"Chat '{args.chat}' not found")
            return
        msgs = await c.get_messages(ent, limit=args.limit)
        for m in reversed(msgs):
            if m.out:
                who = 'ME'
            else:
                s = m.sender
                who = getattr(s, 'first_name', None) or getattr(s, 'title', None) or m.post_author or '?'
            if m.text:
                txt = m.text.replace('\n', ' ')
            elif m.media:
                txt = '[media]'
            else:
                txt = ''
            print(f"[{fmt(m.date)}] {who}: {txt}")
    finally:
        await c.disconnect()

async def send(args):
    c = client()
    await c.connect()
    try:
        ent = await find_chat(c, args.chat)
        if not ent:
            print(f"Chat '{args.chat}' not found")
            return
        await c.send_message(ent, args.text)
        print("Sent OK")
    finally:
        await c.disconnect()

def main():
    p = argparse.ArgumentParser(description='Telegram userbot skill')
    sub = p.add_subparsers(dest='cmd', required=True)
    pl = sub.add_parser('login', help='login (first sends the code, then --code)')
    pl.add_argument('--code')
    pl.add_argument('--password')
    pl.set_defaults(fn=login)
    pc = sub.add_parser('chats', help='list chats')
    pc.add_argument('--limit', type=int, default=60)
    pc.set_defaults(fn=chats)
    pr = sub.add_parser('read', help='read the latest messages of a chat')
    pr.add_argument('chat')
    pr.add_argument('--limit', type=int, default=20)
    pr.set_defaults(fn=read)
    ps = sub.add_parser('send', help='send a message')
    ps.add_argument('chat')
    ps.add_argument('text')
    ps.set_defaults(fn=send)
    args = p.parse_args()
    asyncio.run(args.fn(args))
    sf = BASE / 'tg_session.session'
    if sf.exists():
        sf.chmod(0o600)

if __name__ == '__main__':
    main()
