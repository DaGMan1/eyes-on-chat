"""CDP Web Viewer — manages eyes-on-chat's own Cloak Browser instance via CDP.
Screenshots, clicks, keystrokes, tab management.

Adapted from LeLinc's viewer_api.py -- same pattern (CDP screencast, no VNC
exposed to the end user), but pointed at a completely separate, isolated
`eyes-on-chat-browser` container/profile/port range. Deliberately not shared
with LeLinc's `lelinc-browser` -- Garry was explicit about that.
"""
import json, base64, logging, asyncio, urllib.request
from fastapi import APIRouter, Query, HTTPException, WebSocket
from fastapi.responses import Response
from pydantic import BaseModel
import websockets

log = logging.getLogger("cdp-viewer")

CDP_HTTP = "http://127.0.0.1:19223"

router = APIRouter(prefix="/api/viewer", tags=["viewer"])


class ClickReq(BaseModel):
    x: float
    y: float
    tab_id: str = ""


class NavigateReq(BaseModel):
    url: str
    tab_id: str = ""


class TypeReq(BaseModel):
    text: str
    tab_id: str = ""


class FocusReq(BaseModel):
    tab_id: str


class TabIdReq(BaseModel):
    tab_id: str = ""


def _http_get(path):
    """Sync HTTP GET using stdlib with retry logic."""
    url = f"{CDP_HTTP}{path}"
    for attempt in range(3):
        try:
            with urllib.request.urlopen(url, timeout=15) as r:
                return json.loads(r.read().decode())
        except Exception as e:
            if attempt == 2:
                raise
            log.warning("CDP HTTP attempt %d failed: %s — retrying", attempt + 1, e)
            import time
            time.sleep(1)


async def _http_get_async(path):
    """Async wrapper for sync _http_get, runs in thread to avoid blocking event loop."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _http_get, path)


async def get_tabs():
    return await _http_get_async("/json")


async def get_tab_ws_url(tab_id):
    tabs = await get_tabs()
    if tab_id:
        for t in tabs:
            if t["id"] == tab_id:
                return t["webSocketDebuggerUrl"]
        raise HTTPException(status_code=404, detail="Tab not found")
    return tabs[0]["webSocketDebuggerUrl"] if tabs else None


async def cdp_send_ws(ws_url, method, params=None):
    async with websockets.connect(ws_url) as ws:
        cid = 1
        await ws.send(json.dumps({"id": cid, "method": method, "params": params or {}}))
        async for msg in ws:
            d = json.loads(msg)
            if d.get("id") == cid:
                return d.get("result", {})


@router.get("/tabs")
async def list_tabs():
    """List all open browser tabs (pages only)"""
    tabs = await get_tabs()
    filtered = [
        t for t in tabs
        if t.get("type") == "page"
        and not t.get("url", "").startswith("chrome-extension")
    ]
    return [
        {"id": t["id"], "title": t.get("title", ""), "url": t.get("url", "")}
        for t in filtered
    ]


@router.get("/screenshot")
async def screenshot(tab_id: str = Query(default=""), fmt: str = Query(default="png", alias="format")):
    """Capture a screenshot of a tab via CDP"""
    ws_url = await get_tab_ws_url(tab_id)
    if not ws_url:
        raise HTTPException(status_code=404, detail="No tabs available")
    result = await cdp_send_ws(ws_url, "Page.captureScreenshot",
                               {"format": fmt, "fromSurface": True})
    if not result or "data" not in result:
        raise HTTPException(status_code=500, detail="Screenshot failed")
    return Response(content=base64.b64decode(result["data"]), media_type=f"image/{fmt}")


@router.get("/viewport")
async def viewport(tab_id: str = Query(default="")):
    """Get the viewport dimensions"""
    ws_url = await get_tab_ws_url(tab_id)
    if not ws_url:
        raise HTTPException(status_code=404, detail="No tabs available")
    result = await cdp_send_ws(ws_url, "Page.getLayoutMetrics")
    if not result:
        raise HTTPException(status_code=500, detail="Failed metrics")
    lv = result.get("layoutViewport", {})
    return {"width": lv.get("clientWidth", 1920), "height": lv.get("clientHeight", 1080)}


@router.post("/click")
async def click_tab(req: ClickReq):
    """Click at coordinates (x, y)"""
    ws_url = await get_tab_ws_url(req.tab_id)
    if not ws_url:
        raise HTTPException(status_code=404, detail="No tabs available")
    async with websockets.connect(ws_url) as ws:
        for cid, evt in [(1, "mousePressed"), (2, "mouseReleased")]:
            await ws.send(json.dumps({
                "id": cid, "method": "Input.dispatchMouseEvent",
                "params": {"type": evt, "x": req.x, "y": req.y,
                           "button": "left", "clickCount": 1}
            }))
            async for msg in ws:
                if json.loads(msg).get("id") == cid:
                    break
    return {"status": "clicked", "x": req.x, "y": req.y}


@router.post("/navigate")
async def navigate_tab(req: NavigateReq):
    """Navigate a tab to a URL"""
    ws_url = await get_tab_ws_url(req.tab_id)
    if not ws_url:
        raise HTTPException(status_code=404, detail="No tabs available")
    await cdp_send_ws(ws_url, "Page.navigate", {"url": req.url})
    return {"status": "navigated", "url": req.url}


@router.post("/type")
async def type_text(req: TypeReq):
    """Type text into the focused element"""
    ws_url = await get_tab_ws_url(req.tab_id)
    if not ws_url:
        raise HTTPException(status_code=404, detail="No tabs available")
    async with websockets.connect(ws_url) as ws:
        for i, ch in enumerate(req.text):
            cid1 = i + 1
            await ws.send(json.dumps({
                "id": cid1, "method": "Input.dispatchKeyEvent",
                "params": {"type": "keyDown", "text": ch, "key": ch,
                           "windowsVirtualKeyCode": ord(ch)}
            }))
            async for msg in ws:
                if json.loads(msg).get("id") == cid1:
                    break
            cid2 = i + 10000
            await ws.send(json.dumps({
                "id": cid2, "method": "Input.dispatchKeyEvent",
                "params": {"type": "keyUp", "text": ch, "key": ch,
                           "windowsVirtualKeyCode": ord(ch)}
            }))
            async for msg in ws:
                if json.loads(msg).get("id") == cid2:
                    break
    return {"status": "typed", "chars": len(req.text)}


@router.post("/key")
async def press_key(req: TypeReq):
    """Press a special key (Enter, Tab, Escape, Backspace)"""
    ws_url = await get_tab_ws_url(req.tab_id)
    if not ws_url:
        raise HTTPException(status_code=404, detail="No tabs available")
    key_name = req.text
    vk = 13 if key_name == "Enter" else (9 if key_name == "Tab" else 0)
    async with websockets.connect(ws_url) as ws:
        for cid, evt in [(1, "rawKeyDown"), (2, "keyUp")]:
            await ws.send(json.dumps({
                "id": cid, "method": "Input.dispatchKeyEvent",
                "params": {"type": evt, "key": key_name, "windowsVirtualKeyCode": vk}
            }))
            async for msg in ws:
                if json.loads(msg).get("id") == cid:
                    break
    return {"status": "key_pressed", "key": key_name}


@router.post("/focus")
async def focus_tab(req: FocusReq):
    """Activate / switch to a tab"""
    await _http_get_async(f"/json/activate/{req.tab_id}")
    return {"status": "focused", "tab_id": req.tab_id}


@router.post("/new-tab")
async def new_tab():
    """Create a new blank tab"""
    tab = await _http_get_async("/json/new")
    return {"status": "created", "tab_id": tab.get("id", ""), "title": tab.get("title", "")}


@router.post("/close-tab")
async def close_tab(req: TabIdReq):
    """Close a tab"""
    if not req.tab_id:
        raise HTTPException(status_code=400, detail="tab_id required")
    try:
        await _http_get_async(f"/json/close/{req.tab_id}")
    except Exception:
        pass  # tab may already be gone
    return {"status": "closed", "tab_id": req.tab_id}


@router.post("/close-all")
async def close_all():
    """Close all tabs, leave one blank"""
    for attempt in range(3):
        tabs = await _http_get_async("/json")
        if len(tabs) <= 1:
            break
        for t in tabs:
            try:
                await _http_get_async(f"/json/close/{t['id']}")
            except Exception:
                pass
        await asyncio.sleep(1)
    tab = await _http_get_async("/json/new")
    tabs = await _http_get_async("/json")
    for t in tabs:
        if t["id"] == tab.get("id"):
            continue
        try:
            await _http_get_async(f"/json/close/{t['id']}")
        except Exception:
            pass
    return {"status": "reset", "remaining": 1,
            "tab_id": tab.get("id", ""), "title": tab.get("title", "")}


@router.websocket("/stream")
async def screencast_stream(ws: WebSocket, tab_id: str = ""):
    """CDP screencast bridge — streams live JPEG frames, accepts mouse/keyboard input."""
    await ws.accept()

    tabs = await get_tabs()
    pages = [t for t in tabs if t.get("type") == "page"
             and not t.get("url", "").startswith("chrome-extension")]
    if not pages:
        await ws.close(code=1011, reason="No browser tabs available")
        return

    tab = next((t for t in pages if t["id"] == tab_id), pages[0])
    tab_ws_url = tab["webSocketDebuggerUrl"]

    try:
        async with websockets.connect(tab_ws_url, max_size=20 * 1024 * 1024) as cdp:
            _id = 0

            async def csend(method, params=None):
                nonlocal _id
                _id += 1
                await cdp.send(json.dumps({"id": _id, "method": method, "params": params or {}}))

            await csend("Page.enable")
            await csend("Page.startScreencast", {
                "format": "jpeg", "quality": 80,
                "maxWidth": 1920, "maxHeight": 1080, "everyNthFrame": 1,
            })
            # Request initial URL
            await csend("Runtime.evaluate", {"expression": "location.href"})

            async def cdp_to_client():
                async for raw in cdp:
                    d = json.loads(raw)
                    m = d.get("method", "")

                    if m == "Page.screencastFrame":
                        p = d["params"]
                        await csend("Page.screencastFrameAck", {"sessionId": p["sessionId"]})
                        meta = p.get("metadata", {})
                        try:
                            await ws.send_json({
                                "type": "frame",
                                "data": p["data"],
                                "w": int(meta.get("deviceWidth", 1280)),
                                "h": int(meta.get("deviceHeight", 800)),
                            })
                        except Exception:
                            return

                    elif m == "Page.frameNavigated":
                        frame = d["params"].get("frame", {})
                        if not frame.get("parentId"):
                            try:
                                await ws.send_json({"type": "nav", "url": frame.get("url", "")})
                            except Exception:
                                return

                    elif m == "Page.loadEventFired":
                        await csend("Runtime.evaluate", {"expression": "location.href"})

                    elif d.get("id") and d.get("result", {}).get("result", {}).get("type") == "string":
                        val = d["result"]["result"].get("value", "")
                        if val.startswith("http"):
                            try:
                                await ws.send_json({"type": "nav", "url": val})
                            except Exception:
                                return

            async def client_to_cdp():
                while True:
                    try:
                        msg = await ws.receive_json()
                    except Exception:
                        return
                    t = msg.get("type")
                    if t == "mouse":
                        await csend("Input.dispatchMouseEvent", {
                            "type": msg.get("action", "mousePressed"),
                            "x": float(msg["x"]), "y": float(msg["y"]),
                            "button": msg.get("button", "left"),
                            "clickCount": msg.get("clicks", 1),
                            "modifiers": msg.get("mod", 0),
                            "deltaX": float(msg.get("dx", 0)),
                            "deltaY": float(msg.get("dy", 0)),
                        })
                    elif t == "key":
                        await csend("Input.dispatchKeyEvent", {
                            "type": msg.get("kt", "keyDown"),
                            "key": msg.get("key", ""),
                            "code": msg.get("code", ""),
                            "text": msg.get("text", ""),
                            "modifiers": msg.get("mod", 0),
                            "windowsVirtualKeyCode": msg.get("kc", 0),
                            "nativeVirtualKeyCode": msg.get("kc", 0),
                        })
                    elif t == "navigate":
                        await csend("Page.navigate", {"url": msg["url"]})
                    elif t == "back":
                        await csend("Page.goBack", {})
                    elif t == "forward":
                        await csend("Page.goForward", {})
                    elif t == "reload":
                        await csend("Page.reload", {})

            t1 = asyncio.create_task(cdp_to_client())
            t2 = asyncio.create_task(client_to_cdp())
            done, pending = await asyncio.wait([t1, t2], return_when=asyncio.FIRST_COMPLETED)
            for task in pending:
                task.cancel()
                try:
                    await task
                except Exception:
                    pass

    except Exception as e:
        log.error(f"Screencast stream error: {e}")
        try:
            await ws.send_json({"type": "error", "msg": str(e)})
        except Exception:
            pass