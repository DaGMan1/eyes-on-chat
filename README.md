# eyes-on-chat

A channel and ability for AI agents and people to interact from different platforms — web chat today, Slack/Discord/WhatsApp/Telegram planned via Cloak Browser (see `cdp_integration.py`).

## What's here

- `app.py` — FastAPI server: sessions, messages, the agent-bridge API (`/api/chat/agent/next`, `/api/chat/agent/reply`), WebSocket real-time chat, Web Push, the web chat UI.
- `database.py` — SQLite storage (sessions, messages, agent assignments, push subscriptions, platform connections).
- `cdp_integration.py` — Chrome DevTools Protocol client for Cloak Browser, so a platform (WhatsApp Web, Telegram Web, etc.) logged into a real browser session can be read from / typed into programmatically. Talks to Cloak Browser's CDP endpoint on `127.0.0.1:19223`.
- `static/chat.html` — the chat UI (PWA-installable, Web Push, typing indicator).
- `static/manifest.json`, `static/sw.js`, `static/icons/` — PWA assets.
- `bridge/root_bridge.py` — a snapshot of the agent bridge that polls this server and answers as "ROOT" via the Claude Code CLI. **This is a copy for version control — the live deployed copy runs from `/root/eyes-on-chat-bridge/bridge.py` on a different account (root) for privilege-separation reasons.** Keep them in sync manually when either changes; there's no symlink between them (cross-user permissions).

## Running

```bash
python3 -m venv venv
venv/bin/pip install -r requirements.txt
venv/bin/uvicorn app:app --host 127.0.0.1 --port 8250
```

In production this runs as `eyes-on-chat.service` (systemd), reverse-proxied through Caddy at `hub.keyview.com.au` (Basic Auth) — `chat.keyview.com.au` is a dead domain (no DNS record), don't use it.

## Cloak Browser

`cdp_integration.py`'s `CloakCDP` class talks to the Cloak Browser Docker container (`lelinc-browser`) over CDP. Target discovery (`list_targets`, `create_tab`, `close_tab`) uses CDP's HTTP surface; everything else (`Runtime.evaluate`, i.e. reading/typing into a page) requires a real WebSocket session per CDP's spec — there's no HTTP equivalent, despite how that might look from the `/json/*` endpoints.

## Environment / secrets

Not committed (see `.gitignore`): `vapid_private.pem` (Web Push VAPID key), `chat.db` (runtime data). `vapid_public.txt` is safe to commit (it's public by design).
