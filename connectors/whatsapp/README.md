# 📱 WhatsApp — read and send via your own local bridge

Fast read/send access to **your own WhatsApp account** through a local HTTP bridge. Messages are mirrored in memory by the bridge while it runs (no retroactive history beyond what it has seen).

## Architecture

`wa.py` is a thin client: it queries a small HTTP API served by **your own WhatsApp bridge** (e.g. a Baileys-based Node service running your WhatsApp session) on `127.0.0.1:3789`. The bridge is not part of this repo — you provide it — but the API contract is tiny:

| Endpoint | Returns / does |
|---|---|
| `GET /status` | `{"connected": bool, "messages": N}` |
| `GET /chats` | `[{"name", "count", "last", "lastSender"}, ...]` |
| `GET /messages?hours=&minutes=&chat=&search=&limit=` | `[{"t", "chatName", "name", "text"}, ...]` |
| `GET /send?chat=&text=` | `{"ok": true}` or `{"error": "..."}` |

## Configuration — `.env` (optional)

```ini
# Override the bridge URL (default: http://127.0.0.1:3789)
WA_API_URL=http://127.0.0.1:3789
# Timezone used to display timestamps (default: Europe/Rome)
WA_TZ=Europe/Rome
```

## Dependencies

Only stdlib.

## Usage

```bash
wa.py status                                  # bridge connection status
wa.py chats                                   # list chats with message counts
wa.py read --hours 2                          # last 2 hours of messages
wa.py read --chat "John" --limit 20           # last 20 of a chat
wa.py read --minutes 30 --search "invoice"    # search by text
wa.py send "John" "On my way!"                # send from YOUR account
```

## ⚠️ Safety rules for the agent

- `send` goes out from the **user's real account**: only on explicit user request, never unsolicited, never bulk.
- Read a few recent messages before sending, to match tone and context.
- Multi-part messages can be split with ` || ` if the bridge style supports it.
