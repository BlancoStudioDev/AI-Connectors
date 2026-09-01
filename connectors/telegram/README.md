# 📨 Telegram — read/send from a real user account (Telethon userbot)

Reads and sends messages as **your own Telegram account** (not a bot), via Telethon. First run performs the code/2FA login once; afterwards the session (`tg_session.session`, permission 600) is reused.

## Dependencies

```bash
~/agent-scripts/.venv/bin/pip install telethon
```

## Configuration — `.env`

Get `api_id` / `api_hash` from [my.telegram.org](https://my.telegram.org) → API development tools:

```ini
TG_API_ID=123456
TG_API_HASH=0123456789abcdef0123456789abcdef
TG_PHONE=+39xxxxxxxxxx
```

### One-time login

```bash
telegram.py login                 # sends the code to your Telegram/SMS
telegram.py login --code 12345    # completes login (add --password if 2FA is on)
```

## Usage

```bash
telegram.py chats --limit 60            # list chats (id, name, unread)
telegram.py read "John" --limit 20      # read last 20 messages
telegram.py send "John" "See you soon"  # send from YOUR account
```

Chat names are matched by exact or partial name; ids from `chats` work too.

## ⚠️ Safety rules for the agent

- `send` goes out from the **user's real account**: only on explicit user request, never unsolicited, never bulk.
- Useful for "read that chat", "send him a message" requests.
- `tg_session.session` **is a credential**: never copy it around, never commit it.
