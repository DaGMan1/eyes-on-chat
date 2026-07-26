"""
LeLinc/CoSidekick Unified Chat — FastAPI Server

Endpoints:
  POST   /api/chat/session       — create session
  GET    /api/chat/session/{sid} — get session info
  GET    /api/chat/sessions      — list active sessions
  GET    /api/chat/{sid}/messages  — message history
  POST   /api/chat/{sid}/message   — send message (client or agent)
  POST   /api/chat/cdp/ingest      — CDP ingests a message from Cloak tab
  GET    /api/chat/agent/next      — agent polls for next unread
  POST   /api/chat/agent/reply     — agent sends a reply
  WS     /api/chat/ws/{sid}        — WebSocket real-time chat
  GET    /chat/{sid}               — serve web chat page
  GET    /api/chat/overview        — Q's overview (all conversations)
  GET    /api/chat/vapid-public-key      — public key for Push subscription
  POST   /api/chat/{sid}/push-subscribe  — register a device for push notifications
  GET    /sw.js                          — service worker (root-scoped, for PWA installability + push)
"""
import json
import os
import asyncio
import logging
import time
import uuid
from datetime import datetime

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from pywebpush import webpush, WebPushException

# Import database — works for both `python app.py` and `uvicorn app:app`
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))
import database as db
from viewer_api import router as viewer_router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("chat")

app = FastAPI(title="CoSidekick Unified Chat", version="1.0.0")
app.include_router(viewer_router)

# ============================================================
# WEB PUSH (VAPID)
# ============================================================

_VAPID_PRIVATE_PATH = os.path.join(os.path.dirname(__file__), "vapid_private.pem")
_VAPID_PUBLIC_PATH = os.path.join(os.path.dirname(__file__), "vapid_public.txt")
VAPID_PRIVATE_KEY = open(_VAPID_PRIVATE_PATH).read() if os.path.exists(_VAPID_PRIVATE_PATH) else None
VAPID_PUBLIC_KEY = open(_VAPID_PUBLIC_PATH).read().strip() if os.path.exists(_VAPID_PUBLIC_PATH) else None
VAPID_CLAIMS = {"sub": "mailto:garry@keyview.com.au"}


def send_push(session_id: str, title: str, body: str):
    """Best-effort: notify every device subscribed to this session. Never raises --
    a push failure must not break the chat reply it's attached to."""
    if not VAPID_PRIVATE_KEY:
        return
    for sub in db.get_push_subscriptions(session_id):
        try:
            webpush(
                subscription_info={
                    "endpoint": sub["endpoint"],
                    "keys": {"p256dh": sub["p256dh"], "auth": sub["auth"]},
                },
                data=json.dumps({
                    "title": title,
                    "body": body[:180],
                    "url": f"/chat/{session_id}",
                    "session_id": session_id,
                }),
                vapid_private_key=VAPID_PRIVATE_KEY,
                vapid_claims=dict(VAPID_CLAIMS),
            )
        except WebPushException as e:
            status = getattr(e.response, "status_code", None)
            if status in (404, 410):
                db.remove_push_subscription(sub["endpoint"])
            else:
                logger.warning("push failed for session %s: %s", session_id, e)
        except Exception as e:
            logger.warning("push failed for session %s: %s", session_id, e)


# ============================================================
# WEBSOCKET CONNECTIONS
# ============================================================

class ConnectionManager:
    """Manages WebSocket connections per session."""
    def __init__(self):
        # {session_id: [websocket, ...]}
        self.active_connections: dict[str, list[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, session_id: str):
        await websocket.accept()
        if session_id not in self.active_connections:
            self.active_connections[session_id] = []
        self.active_connections[session_id].append(websocket)

    def disconnect(self, websocket: WebSocket, session_id: str):
        if session_id in self.active_connections:
            self.active_connections[session_id] = [ws for ws in self.active_connections[session_id] if ws != websocket]
            if not self.active_connections[session_id]:
                del self.active_connections[session_id]

    async def broadcast(self, session_id: str, message: dict):
        """Send message to all connected clients in a session."""
        if session_id not in self.active_connections:
            return
        dead = []
        for ws in self.active_connections[session_id]:
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws, session_id)

manager = ConnectionManager()

# Watches connected platform tabs (WhatsApp Web, Telegram Web, etc.) via
# Cloak Browser CDP and forwards new messages into this server. Created at
# startup (needs an event loop); stays None until then, so anything using it
# must check for that (see /api/platforms/connect).
platform_watcher = None


# ============================================================
# API MODELS
# ============================================================

class CreateSessionRequest(BaseModel):
    client_name: str
    client_email: str
    business_name: str = ""
    product: str = "kvd"

class SendMessageRequest(BaseModel):
    content: str
    sender: str = "client"
    sender_name: str = ""
    platform: str = "webchat"
    message_type: str = "text"
    platform_message_id: str = ""

class CDPIngestRequest(BaseModel):
    session_id: str
    platform: str
    content: str
    sender: str = "client"
    sender_name: str = ""
    platform_message_id: str = ""

class PlatformConnectRequest(BaseModel):
    platform: str
    tab_id: str = ""
    # No session picker in the UI yet -- there's only one real session (ROOT's)
    # right now, so new platform connections default to it. Revisit once
    # there's an actual multi-session routing model for incoming platform
    # messages (which agent/session should WhatsApp messages go to?).
    session_id: str = "b4d94cbd-ed57-4f3f-a374-77730a74b166"

class AgentReplyRequest(BaseModel):
    session_id: str
    content: str
    agent_name: str = "cosidekick"
    message_type: str = "text"

class AgentTypingRequest(BaseModel):
    session_id: str
    agent_name: str = "agent"
    is_typing: bool = True

class PushSubscriptionKeys(BaseModel):
    p256dh: str
    auth: str

class PushSubscribeRequest(BaseModel):
    endpoint: str
    keys: PushSubscriptionKeys


# ============================================================
# ROUTES
# ============================================================

@app.post("/api/chat/session")
async def create_session(req: CreateSessionRequest):
    """Create a new chat session. Returns session + QR code data."""
    session = db.create_session(
        client_name=req.client_name,
        client_email=req.client_email,
        business_name=req.business_name,
        product=req.product
    )
    if not session:
        raise HTTPException(500, "Failed to create session")

    # Generate QR code data
    qr_data = db.generate_qr_data(session["id"])

    # Add system welcome message
    db.add_message(
        session_id=session["id"],
        platform="system",
        sender="system",
        sender_name="CoSidekick",
        content=f"Welcome {req.client_name}! Your agent is ready to help. How can I assist you today?",
        message_type="system"
    )

    return {
        "session_id": session["id"],
        "qr_code_data": qr_data,
        "qr_code_url": f"https://api.qrserver.com/v1/create-qr-code/?size=300x300&data={qr_data}",
        "chat_url": f"/chat/{session['id']}",
        "session": dict(session)
    }


@app.get("/api/chat/session/{session_id}")
async def get_session(session_id: str):
    """Get session info."""
    session = db.get_session(session_id)
    if not session:
        raise HTTPException(404, "Session not found")

    agent = db.get_current_agent(session_id)
    return {
        "session": session,
        "agent": agent
    }


@app.get("/api/chat/sessions")
async def list_sessions(product: str = None, status: str = "active"):
    """List active sessions, optionally filtered by product."""
    sessions = db.list_active_sessions(product)
    result = []
    for s in sessions:
        last_msg = db.get_latest_message(s["id"])
        unread = len(db.get_unread_messages(session_id=s["id"]))
        result.append({
            "session": s,
            "last_message": last_msg,
            "unread_count": unread
        })
    return {"sessions": result, "count": len(result)}


@app.get("/api/chat/{session_id}/messages")
async def get_messages(session_id: str, limit: int = 50, offset: int = 0):
    """Get message history."""
    messages = db.get_messages(session_id, limit=limit, offset=offset)
    return {
        "session_id": session_id,
        "messages": list(reversed(messages)),  # chronological order
        "count": len(messages)
    }


@app.post("/api/chat/{session_id}/message")
async def send_message(session_id: str, req: SendMessageRequest):
    """Send a message from client or web chat."""
    session = db.get_session(session_id)
    if not session:
        raise HTTPException(404, "Session not found")

    msg = db.add_message(
        session_id=session_id,
        platform=req.platform,
        sender=req.sender,
        sender_name=req.sender_name or req.sender,
        content=req.content,
        message_type=req.message_type,
        platform_message_id=req.platform_message_id
    )

    # Broadcast via WebSocket
    await manager.broadcast(session_id, {
        "type": "message",
        "id": msg["id"],
        "sender": msg["sender"],
        "sender_name": msg["sender_name"],
        "content": msg["content"],
        "platform": msg["platform"],
        "created_at": msg["created_at"]
    })

    # Fire-and-forget auto-reply: ask the LLM agent to respond.
    try:
        import asyncio as _aio
        _aio.create_task(_auto_reply_dispatch(session_id, req.content, req.sender))
    except Exception as _e:
        logger.exception("auto-reply schedule failed: %s", _e)

    return {"message": msg}



@app.post("/api/chat/cdp/ingest")
async def cdp_ingest(req: CDPIngestRequest):
    """CDP layer ingests a message from a Cloak browser tab."""
    session = db.get_session(req.session_id)
    if not session:
        raise HTTPException(404, "Session not found")

    msg = db.add_message(
        session_id=req.session_id,
        platform=req.platform,
        sender=req.sender,
        sender_name=req.sender_name,
        content=req.content,
        platform_message_id=req.platform_message_id
    )

    # Broadcast via WebSocket
    await manager.broadcast(req.session_id, {
        "type": "message",
        "id": msg["id"],
        "sender": msg["sender"],
        "sender_name": msg["sender_name"],
        "content": msg["content"],
        "platform": msg["platform"],
        "created_at": msg["created_at"]
    })

    return {"message": msg}


@app.post("/api/platforms/connect")
async def connect_platform(req: PlatformConnectRequest):
    """Register a Cloak Browser tab as a connected platform, and start
    watching it for new messages (forwarded to /api/chat/cdp/ingest)."""
    session = db.get_session(req.session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    if not req.tab_id:
        raise HTTPException(400, "No browser tab open to connect -- navigate to the platform first")

    db.add_connection(req.session_id, req.platform, req.tab_id)

    if platform_watcher is not None:
        await platform_watcher.register_tab_by_id(req.session_id, req.platform, req.tab_id)

    return {"status": "connected", "platform": req.platform, "tab_id": req.tab_id}


@app.get("/api/chat/agent/next")
async def agent_next(
    agent_name: str = Query("cosidekick"),
    mark_read: bool = Query(True),
    wait: int = Query(0, description="Long-poll: seconds to block waiting for a new message"),
):
    """Agent polls for the next unread message. With wait>0, long-polls up to N seconds."""
    import asyncio as _aio_lp
    deadline = time.monotonic() + max(0, min(wait, 60))
    while True:
        messages = db.get_unread_messages(agent_name=agent_name)
        if messages:
            msg = messages[0]
            if mark_read:
                db.mark_read(msg["session_id"], [msg["id"]])
            session = db.get_session(msg["session_id"])
            return {"message": msg, "session": session}
        if time.monotonic() >= deadline:
            return {"message": None}
        await _aio_lp.sleep(1)


@app.post("/api/chat/agent/reply")
async def agent_reply(req: AgentReplyRequest):
    """Agent sends a reply. Also broadcasts via WebSocket."""
    session = db.get_session(req.session_id)
    if not session:
        raise HTTPException(404, "Session not found")

    msg = db.add_message(
        session_id=req.session_id,
        platform="agent",
        sender="agent",
        sender_name=req.agent_name,
        content=req.content,
        message_type=req.message_type
    )

    # Broadcast to client
    await manager.broadcast(req.session_id, {
        "type": "message",
        "id": msg["id"],
        "sender": "agent",
        "sender_name": req.agent_name,
        "content": req.content,
        "message_type": req.message_type,
        "platform": "agent",
        "created_at": msg["created_at"]
    })

    send_push(req.session_id, req.agent_name, req.content)

    return {"message": msg}


@app.post("/api/chat/agent/typing")
async def agent_typing(req: AgentTypingRequest):
    """Agent signals it's working on a reply, so the client sees a typing
    indicator instead of a blank screen during long (multi-minute) processing."""
    await manager.broadcast(req.session_id, {
        "type": "typing",
        "sender": "agent",
        "sender_name": req.agent_name,
        "is_typing": req.is_typing,
    })
    return {"status": "ok"}


@app.get("/api/chat/vapid-public-key")
async def vapid_public_key():
    """Public key the client needs to create a PushManager subscription."""
    if not VAPID_PUBLIC_KEY:
        raise HTTPException(503, "Push not configured on this server")
    return {"publicKey": VAPID_PUBLIC_KEY}


@app.post("/api/chat/{session_id}/push-subscribe")
async def push_subscribe(session_id: str, req: PushSubscribeRequest):
    """Register a device's push subscription for this session."""
    session = db.get_session(session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    db.add_push_subscription(session_id, req.endpoint, req.keys.p256dh, req.keys.auth)
    return {"status": "subscribed"}


@app.post("/api/chat/{session_id}/handoff")
async def handoff_agent(session_id: str, new_agent: str, reason: str = ""):
    """Hand off a session to another agent."""
    session = db.get_session(session_id)
    if not session:
        raise HTTPException(404, "Session not found")

    old_agent = db.get_current_agent(session_id)
    db.assign_agent(session_id, new_agent, role="primary")

    # Notify client
    handoff_msg = f"Handing over to {new_agent}"
    if reason:
        handoff_msg += f" — {reason}"
    db.add_message(
        session_id=session_id,
        platform="system",
        sender="system",
        sender_name="System",
        content=handoff_msg,
        message_type="system"
    )

    await manager.broadcast(session_id, {
        "type": "agent_change",
        "old_agent": old_agent["agent_name"] if old_agent else None,
        "new_agent": new_agent,
        "reason": reason
    })

    return {"status": "handed_off", "old_agent": old_agent["agent_name"] if old_agent else None, "new_agent": new_agent}


@app.get("/api/chat/overview")
async def overview():
    """Q's dashboard — overview of all conversations."""
    sessions = db.list_active_sessions()
    result = []
    for s in sessions:
        last_msg = db.get_latest_message(s["id"])
        unread = db.get_unread_messages(session_id=s["id"])
        agent = db.get_current_agent(s["id"])
        result.append({
            "session_id": s["id"],
            "client_name": s["client_name"],
            "product": s["product"],
            "status": s["status"],
            "current_agent": agent["agent_name"] if agent else None,
            "last_message": last_msg["content"][:100] if last_msg else None,
            "last_message_time": last_msg["created_at"] if last_msg else None,
            "unread_count": len(unread)
        })

    return {
        "total_active": len(result),
        "total_unread": sum(r["unread_count"] for r in result),
        "conversations": result
    }


# ============================================================
# WEB CHAT FRONTEND
# ============================================================

# ============================================================
# LANDING PAGE — create a new session
# ============================================================

LANDING_HTML_DOC = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no">
<title>eyes-on-chat</title>
<link rel="manifest" href="/static/manifest.json">
<meta name="theme-color" content="#0b0b0f">
<link rel="apple-touch-icon" href="/static/icons/icon-192.png">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-title" content="eyes-on-chat">
<style>
  :root { --bg:#0b0b0f; --panel:#14141a; --border:#2a2a36; --text:#e8e8ee; --muted:#8888a0; --accent:#6c5ce7; }
  * { box-sizing: border-box; }
  body { margin:0; background:var(--bg); color:var(--text); font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; min-height:100vh; display:flex; align-items:center; justify-content:center; padding:24px; }
  .wrap { max-width:420px; width:100%; }
  .tag { color:var(--accent); font-size:11px; letter-spacing:0.1em; text-transform:uppercase; margin-bottom:8px; text-align:center; }
  h1 { margin:0 0 28px; font-size:20px; text-align:center; font-weight:600; }
  .picker { display:flex; flex-direction:column; gap:12px; }
  .agent-link { display:flex; align-items:center; gap:14px; padding:18px 20px; background:var(--panel); border:1px solid var(--border); border-radius:14px; color:var(--text); text-decoration:none; }
  .agent-link:active { border-color:var(--accent); }
  .avatar { width:44px; height:44px; border-radius:12px; background:var(--accent); display:flex; align-items:center; justify-content:center; font-weight:700; font-size:16px; flex-shrink:0; }
  .info .name { font-weight:600; font-size:15px; }
  .info .desc { font-size:12px; color:var(--muted); margin-top:2px; }
</style>
</head>
<body>
<div class="wrap">
  <div class="tag">eyes-on-chat</div>
  <h1>Who do you want to talk to?</h1>
  <div class="picker">
    <a class="agent-link" href="/chat/b4d94cbd-ed57-4f3f-a374-77730a74b166">
      <div class="avatar">R</div>
      <div class="info"><div class="name">ROOT</div><div class="desc">VP — build, infra, direct work</div></div>
    </a>
  </div>
</div>
<script>
if ("serviceWorker" in navigator) { navigator.serviceWorker.register("/sw.js", { scope: "/" }).catch(() => {}); }
</script>
</body>
</html>
"""

@app.get("/chat", response_class=HTMLResponse)
@app.get("/chat/", response_class=HTMLResponse)
async def chat_landing():
    """Landing page — list existing sessions + create new."""
    return HTMLResponse(LANDING_HTML_DOC)

@app.get("/chat/{session_id}", response_class=HTMLResponse)
async def chat_page(session_id: str):
    """Serve the web chat page."""
    session = db.get_session(session_id)
    if not session:
        return HTMLResponse("<h1>Session not found</h1>", status_code=404)

    html_path = os.path.join(os.path.dirname(__file__), "static", "chat.html")
    if not os.path.exists(html_path):
        return HTMLResponse("<h1>Chat UI not built yet</h1>", status_code=501)

    with open(html_path) as f:
        html = f.read()

    # Inject session data
    html = html.replace("{{SESSION_ID}}", session_id)
    html = html.replace("{{CLIENT_NAME}}", session["client_name"])

    return HTMLResponse(html)


# ============================================================
# WEBSOCKET
# ============================================================

@app.websocket("/api/chat/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    """WebSocket for real-time messaging."""
    session = db.get_session(session_id)
    if not session:
        await websocket.close(code=4004, reason="Session not found")
        return

    await manager.connect(websocket, session_id)

    try:
        while True:
            data = await websocket.receive_json()

            if data.get("type") == "message":
                # Client sent a message
                content = data.get("content", "").strip()
                if content:
                    msg = db.add_message(
                        session_id=session_id,
                        platform="webchat",
                        sender="client",
                        sender_name=session["client_name"],
                        content=content
                    )
                    # Echo back as confirmation + broadcast to agent
                    await websocket.send_json({
                        "type": "message",
                        "id": msg["id"],
                        "sender": "client",
                        "sender_name": session["client_name"],
                        "content": content,
                        "platform": "webchat",
                        "created_at": msg["created_at"]
                    })

            elif data.get("type") == "typing":
                # Forward typing indicator
                await manager.broadcast(session_id, {
                    "type": "typing",
                    "sender": "client",
                    "is_typing": data.get("is_typing", False)
                })

            elif data.get("type") == "read":
                # Mark messages as read
                msg_ids = data.get("message_ids", [])
                db.mark_read(session_id, msg_ids)

    except WebSocketDisconnect:
        manager.disconnect(websocket, session_id)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        manager.disconnect(websocket, session_id)


# ============================================================
# HEALTH
# ============================================================

@app.get("/health")
async def health():
    return {"status": "ok", "service": "cosidekick-chat"}


@app.get("/platforms", response_class=HTMLResponse)
async def platforms_page():
    """Garry's own admin page: live view of eyes-on-chat's isolated Cloak
    Browser tab, pick a platform, log in, mark it connected. Not a CoSidekick
    end-user page -- put behind the same auth as the rest of the admin
    surface (hub.keyview.com.au's Basic Auth), not exposed on its own."""
    path = os.path.join(os.path.dirname(__file__), "static", "platforms.html")
    if not os.path.exists(path):
        return HTMLResponse("<h1>Not built yet</h1>", status_code=501)
    with open(path) as f:
        return HTMLResponse(f.read())


@app.get("/api/platforms/status")
async def platforms_status():
    """What's actually connected, per the database -- not just what the
    browser happens to be logged into (those are different things)."""
    return {"connections": db.list_connections()}


@app.get("/platforms/status", response_class=HTMLResponse)
async def platforms_status_page():
    """Read-only status view: what's connected, when it last had activity.
    Separate from /platforms (which is the live connect flow) on purpose --
    this is "what's hooked up right now", not "go log into something"."""
    path = os.path.join(os.path.dirname(__file__), "static", "platforms_status.html")
    if not os.path.exists(path):
        return HTMLResponse("<h1>Not built yet</h1>", status_code=501)
    with open(path) as f:
        return HTMLResponse(f.read())


@app.get("/sw.js")
async def service_worker():
    """Served at the root path (not /static/sw.js) so its default scope covers
    the whole site, including /chat/<session_id> -- a service worker's scope
    can't exceed the directory it's served from without this."""
    path = os.path.join(os.path.dirname(__file__), "static", "sw.js")
    return FileResponse(path, media_type="application/javascript",
                         headers={"Service-Worker-Allowed": "/", "Cache-Control": "no-cache"})


# ============================================================
# STATIC FILES
# ============================================================

static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")


# ============================================================
# STARTUP
# ============================================================

# ============================================================
# LLM AUTO-REPLY (background task)
# ============================================================

async def _auto_reply_dispatch(session_id: str, client_message: str, sender: str):
    """Background coroutine: ask the LLM agent to respond to a client message."""
    logger.info("auto-reply: start session=%s sender=%s msg=%s",
                session_id, sender, (client_message or "")[:80])
    try:
        if sender not in ("client", "user"):
            logger.info("auto-reply: skip non-client sender")
            return
        text = (client_message or "").strip()
        if not text or len(text) > 4000:
            logger.info("auto-reply: empty or too long")
            return
        session = db.get_session(session_id)
        if not session:
            logger.info("auto-reply: session not found")
            return
        # Sessions handed off to a real polling agent (e.g. "root") must not also
        # get this generic stub reply — it isn't the real agent, just a placeholder
        # that predates the agent-bridge API. Only fire for sessions still on the
        # original default assignment.
        current_agent = db.get_current_agent(session_id)
        if current_agent and current_agent.get("agent_name") not in (None, "cosidekick"):
            logger.info("auto-reply: skip, session handed off to %s", current_agent.get("agent_name"))
            return
        history = db.get_messages(session_id, limit=10) or []
        msgs = [{"role": "system", "content":
            f"You are Q, the chief of staff for Garry at Key View. "
            f"Customer: {session.get('client_name','unknown')}. "
            f"Business: {session.get('business_name','')}. "
            f"Respond in 1-3 short sentences. Be direct, warm, no fluff."}]
        for m in history[-10:]:
            role = "user" if m.get("sender") in ("client", "user") else "assistant"
            msgs.append({"role": role, "content": m.get("content", "")[:500]})
        msgs.append({"role": "user", "content": text})
        reply_text = _call_llm(msgs)
        if not reply_text:
            logger.info("auto-reply: empty reply")
            return
        db.add_message(
            session_id=session_id,
            platform="webchat",
            sender="agent",
            sender_name="Q",
            content=reply_text,
            message_type="text",
        )
        send_push(session_id, "Q", reply_text)
        logger.info("auto-reply: stored (%d chars)", len(reply_text))
        try:
            await manager.broadcast(session_id,
                {"type": "message", "sender": "agent", "sender_name": "Q",
                 "content": reply_text})
        except Exception as _we:
            logger.warning("auto-reply broadcast failed: %s", _we)
    except Exception as _e:
        logger.exception("auto-reply crashed: %s", _e)


def _call_llm(messages):
    """Call OpenRouter / OpenAI chat completion. Tries cheap model first."""
    import os as _os, json as _json, urllib.request as _urlreq
    import urllib.error
    api_key = _os.environ.get("OPENROUTER_API_KEY") or _os.environ.get("OPENAI_API_KEY") or ""
    if not api_key:
        logger.warning("LLM call: no API key")
        return None

    # Cheap models first, then fall back to sonnet
    models = [
        _os.environ.get("EYES_CHAT_MODEL", ""),
        "anthropic/claude-3.5-haiku",
        "anthropic/claude-3-haiku",
        "openai/gpt-4o-mini",
        "anthropic/claude-sonnet-4",
    ]
    models = [m for m in models if m]

    last_err = None
    for model in models:
        try:
            body = _json.dumps({
                "model": model,
                "messages": messages,
                "max_tokens": 300,
            }).encode()
            req = _urlreq.Request(
                "https://openrouter.ai/api/v1/chat/completions",
                data=body,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://hub.keyview.com.au/chat",
                },
            )
            with _urlreq.urlopen(req, timeout=20) as resp:
                data = _json.loads(resp.read().decode())
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
            if content:
                logger.info("LLM call: model=%s, content chars=%d", model, len(content))
                return content
        except urllib.error.HTTPError as e:
            err_body = e.read().decode()[:200] if hasattr(e, "read") else str(e)
            logger.warning("LLM call model=%s HTTP %s: %s", model, e.code, err_body)
            last_err = e
        except Exception as e:
            logger.warning("LLM call model=%s failed: %s", model, e)
            last_err = e
    return None


@app.on_event("startup")
async def startup():
    db.init_db()
    logger.info("Chat database initialized")

    global platform_watcher
    from cdp_integration import create_watcher
    platform_watcher = create_watcher()
    asyncio.create_task(platform_watcher.poll_loop())
    logger.info("Platform watcher started (Cloak Browser CDP)")


# ============================================================
# MAIN (for direct execution)
# ============================================================

if __name__ == "__main__":
    import uvicorn
    db.init_db()
    uvicorn.run(app, host="0.0.0.0", port=8250)