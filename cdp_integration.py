"""
LeLinc/CoSidekick CDP Integration Layer

Reads messages from Cloak Browser tabs (WhatsApp Web, Telegram Web, etc.)
and types replies back using Chrome DevTools Protocol.

Requires: Cloak Browser running with CDP port exposed. The `lelinc-browser`
container maps CDP to 127.0.0.1:19222 (NOT 9222 -- 9222 resets the
connection; confirmed directly against the running container, not assumed).
"""
import asyncio
import itertools
import json
import logging
from typing import Any, Optional

import httpx
import websockets

logger = logging.getLogger("cdp")

CDP_COMMAND_TIMEOUT = 10.0

# ============================================================
# CLIENT
# ============================================================

class CloakCDP:
    """
    CDP client for Cloak Browser. Target discovery (list/create/close tabs)
    goes over CDP's plain HTTP endpoints; JS evaluation requires a real CDP
    session, which only exists over WebSocket -- there is no HTTP equivalent
    for Runtime.evaluate, despite how that might look from the /json/* HTTP
    surface. A previous version of this file tried to POST to a devtools/page
    HTTP path for it, which silently did nothing (unreachable code path,
    never actually exercised against a live browser).
    """

    def __init__(self, cdp_url: str = "http://127.0.0.1:19222"):
        self.cdp_url = cdp_url
        self.ws_host = cdp_url.replace("http://", "ws://").replace("https://", "wss://")
        self.http = httpx.AsyncClient(timeout=15.0)
        self._id_counter = itertools.count(1)

    async def close(self):
        await self.http.aclose()

    # ----------------------------------------------------------
    # TARGET MANAGEMENT (HTTP -- this part of CDP is genuinely HTTP)
    # ----------------------------------------------------------

    async def list_targets(self) -> list[dict]:
        """List all open tabs/targets."""
        try:
            resp = await self.http.get(f"{self.cdp_url}/json/list")
            return resp.json()
        except Exception as e:
            logger.error("Failed to list CDP targets: %s", e)
            return []

    async def find_or_create_tab(self, url_pattern: str) -> Optional[dict]:
        """Find a tab whose URL contains url_pattern."""
        targets = await self.list_targets()
        for t in targets:
            if url_pattern.lower() in t.get("url", "").lower():
                return t
        return None

    async def create_tab(self, url: str) -> Optional[dict]:
        """Create a new tab and navigate to URL."""
        try:
            resp = await self.http.put(f"{self.cdp_url}/json/new", params={"": url})
            return resp.json()
        except Exception as e:
            logger.error("Failed to create tab: %s", e)
            return None

    async def close_tab(self, target_id: str):
        """Close a tab by target ID."""
        try:
            await self.http.get(f"{self.cdp_url}/json/close/{target_id}")
        except Exception as e:
            logger.error("Failed to close tab: %s", e)

    # ----------------------------------------------------------
    # CDP COMMANDS (WebSocket -- the only real way to call methods
    # like Runtime.evaluate against a specific page)
    # ----------------------------------------------------------

    async def send_command(self, target_id: str, method: str, params: Optional[dict] = None) -> dict[str, Any]:
        """Open a short-lived CDP WebSocket session to a page and send one command.
        A fresh connection per call is simpler and more robust than a pooled/
        persistent one for this system's polling cadence (every few seconds),
        at the cost of a bit of per-call latency -- acceptable trade-off here."""
        ws_url = f"{self.ws_host}/devtools/page/{target_id}"
        request_id = next(self._id_counter)
        payload = {"id": request_id, "method": method, "params": params or {}}
        try:
            async with websockets.connect(ws_url, open_timeout=CDP_COMMAND_TIMEOUT) as ws:
                await ws.send(json.dumps(payload))
                async with asyncio.timeout(CDP_COMMAND_TIMEOUT):
                    while True:
                        raw = await ws.recv()
                        message = json.loads(raw)
                        # CDP multiplexes events onto the same socket; skip
                        # anything that isn't the response to our own request.
                        if message.get("id") == request_id:
                            return message
        except Exception as e:
            logger.error("CDP command failed %s: %s", method, e)
            return {}

    async def evaluate(self, target_id: str, expression: str) -> str:
        """Evaluate JavaScript in a tab. Returns the result as a string
        (CDP's returnByValue coerces the JS return value into JSON)."""
        result = await self.send_command(
            target_id,
            "Runtime.evaluate",
            {"expression": expression, "returnByValue": True}
        )
        if "error" in result:
            logger.error("Runtime.evaluate error: %s", result["error"])
            return ""
        try:
            return result.get("result", {}).get("result", {}).get("value", "")
        except Exception:
            return ""
    
    # ----------------------------------------------------------
    # PLATFORM-SPECIFIC: WHATSAPP WEB
    # ----------------------------------------------------------
    
    WHATSAPP_CHAT_SELECTOR = "div[role='row'][tabindex='-1']"
    WHATSAPP_MESSAGE_SELECTOR = ".message-in span.selectable-text, .message-out span.selectable-text"
    WHATSAPP_INPUT_SELECTOR = "div[contenteditable='true'][spellcheck='true']"
    
    async def get_whatsapp_messages(self, target_id: str) -> list[dict]:
        """Get visible messages from WhatsApp Web tab."""
        js = """
        (() => {
            const msgs = document.querySelectorAll('.message-in span.selectable-text, .message-out span.selectable-text');
            return Array.from(msgs).map(el => ({
                text: el.innerText.trim(),
                sender: el.closest('.message-in') ? 'client' : 'self'
            }));
        })()
        """
        # returnByValue already gives back a decoded Python list -- no
        # json.loads needed (a previous version of this code did an extra
        # json.loads() here, which would raise on an already-decoded list).
        result = await self.evaluate(target_id, js)
        return result if isinstance(result, list) else []
    
    async def send_whatsapp_reply(self, target_id: str, text: str) -> bool:
        """Type a reply into WhatsApp Web and send it."""
        escaped = text.replace("'", "\\'").replace("\n", "\\n")
        js = f"""
        (() => {{
            const input = document.querySelector('div[contenteditable="true"][spellcheck="true"]');
            if (!input) return false;
            
            // Focus and clear
            input.focus();
            input.innerHTML = '';
            
            // Paste text
            const textNode = document.createTextNode('{escaped}');
            input.appendChild(textNode);
            
            // Trigger input event
            input.dispatchEvent(new Event('input', {{ bubbles: true }}));
            
            // Find and click send button
            const sendBtn = document.querySelector('button[aria-label="Send"]') || 
                            document.querySelector('span[data-icon="send"]');
            if (sendBtn) {{
                sendBtn.click();
                return true;
            }}
            
            // Fallback: press Enter
            const event = new KeyboardEvent('keydown', {{ key: 'Enter', code: 'Enter', which: 13, keyCode: 13, bubbles: true }});
            input.dispatchEvent(event);
            return true;
        }})()
        """
        # returnByValue decodes a JS boolean straight to a Python bool --
        # comparing against the string "true" (as a previous version did)
        # would always be False.
        result = await self.evaluate(target_id, js)
        return result is True

    # ----------------------------------------------------------
    # PLATFORM-SPECIFIC: TELEGRAM WEB
    # ----------------------------------------------------------
    
    TELEGRAM_MESSAGE_SELECTOR = ".bubble.is-in .text, .bubble.is-out .text"
    TELEGRAM_INPUT_SELECTOR = ".input-message-input"
    
    async def get_telegram_messages(self, target_id: str) -> list[dict]:
        """Get visible messages from Telegram Web tab."""
        js = """
        (() => {
            const msgs = document.querySelectorAll('.bubble .text');
            return Array.from(msgs).map(el => ({
                text: el.innerText.trim(),
                sender: el.closest('.is-in') ? 'client' : 'self'
            }));
        })()
        """
        result = await self.evaluate(target_id, js)
        return result if isinstance(result, list) else []
    
    async def send_telegram_reply(self, target_id: str, text: str) -> bool:
        """Type a reply into Telegram Web and send it."""
        escaped = text.replace("'", "\\'").replace("\n", "\\n")
        js = f"""
        (() => {{
            const input = document.querySelector('.input-message-input');
            if (!input) return false;
            input.focus();
            input.innerHTML = '';
            const textNode = document.createTextNode('{escaped}');
            input.appendChild(textNode);
            input.dispatchEvent(new Event('input', {{ bubbles: true }}));
            
            // Press Enter
            const event = new KeyboardEvent('keydown', {{ key: 'Enter', code: 'Enter', which: 13, keyCode: 13, bubbles: true }});
            input.dispatchEvent(event);
            return true;
        }})()
        """
        result = await self.evaluate(target_id, js)
        return result is True
    
    # ----------------------------------------------------------
    # GENERIC PLATFORM SUPPORT
    # ----------------------------------------------------------
    
    async def detect_new_messages(self, target_id: str, platform: str, last_known_count: int = 0) -> list:
        """
        Generic message detection. Returns new messages since last check.
        Platform determines which selectors to use.
        """
        if platform == "whatsapp":
            msgs = await self.get_whatsapp_messages(target_id)
        elif platform == "telegram":
            msgs = await self.get_telegram_messages(target_id)
        else:
            # Generic: grab all text content from the page body
            js = "document.body.innerText.substring(0, 10000)"
            text = await self.evaluate(target_id, js)
            return [{"text": text, "sender": "unknown"}]
        
        # Filter to only client messages (not self)
        client_msgs = [m for m in msgs if m.get("sender") == "client"]
        
        # If there are more client messages than last time, they're new
        if len(client_msgs) > last_known_count:
            return client_msgs[last_known_count:]
        return []
    
    async def send_reply(self, target_id: str, platform: str, text: str) -> bool:
        """Send a reply via the appropriate platform."""
        if platform == "whatsapp":
            return await self.send_whatsapp_reply(target_id, text)
        elif platform == "telegram":
            return await self.send_telegram_reply(target_id, text)
        else:
            logger.warning(f"No reply handler for platform: {platform}")
            return False


# ============================================================
# WATCHER — Polls Cloak tabs for new messages
# ============================================================

class PlatformWatcher:
    """
    Watches a Cloak browser tab for new messages and forwards them
    to the chat API.
    """
    
    def __init__(self, cdp: CloakCDP, chat_api_url: str = "http://127.0.0.1:8250"):
        self.cdp = cdp
        self.chat_api_url = chat_api_url
        self.http = httpx.AsyncClient(timeout=10.0)
        self._tabs = {}  # {session_id: {platform: {target_id, last_count}}}
    
    async def register_tab(self, session_id: str, platform: str, url_pattern: str):
        """Register a platform tab to watch for a session."""
        tab = await self.cdp.find_or_create_tab(url_pattern)
        if not tab:
            logger.warning(f"No tab found for {platform} ({url_pattern})")
            return False
        
        target_id = tab["id"]
        if session_id not in self._tabs:
            self._tabs[session_id] = {}
        
        self._tabs[session_id][platform] = {
            "target_id": target_id,
            "last_count": 0
        }
        
        logger.info(f"Watching {platform} for session {session_id} (tab: {target_id})")
        return True
    
    async def poll_once(self):
        """Poll all registered tabs for new messages."""
        for session_id, platforms in list(self._tabs.items()):
            for platform, state in list(platforms.items()):
                try:
                    new_msgs = await self.cdp.detect_new_messages(
                        state["target_id"],
                        platform,
                        state["last_count"]
                    )
                    
                    for msg in new_msgs:
                        # Forward to chat API
                        await self.http.post(
                            f"{self.chat_api_url}/api/chat/cdp/ingest",
                            json={
                                "session_id": session_id,
                                "platform": platform,
                                "content": msg["text"],
                                "sender": "client",
                                "sender_name": "Client (via " + platform + ")"
                            }
                        )
                    
                    state["last_count"] += len(new_msgs)
                    
                except Exception as e:
                    logger.error(f"Poll error [{session_id}/{platform}]: {e}")
    
    async def poll_loop(self, interval: float = 5.0):
        """Continuously poll tabs for new messages."""
        logger.info(f"Starting CDP watcher loop (interval: {interval}s)")
        while True:
            await self.poll_once()
            await asyncio.sleep(interval)
    
    async def send_to_platform(self, session_id: str, platform: str, text: str) -> bool:
        """Send a reply to a platform tab."""
        if session_id not in self._tabs or platform not in self._tabs[session_id]:
            logger.warning(f"No tab registered for {session_id}/{platform}")
            return False
        
        state = self._tabs[session_id][platform]
        return await self.cdp.send_reply(state["target_id"], platform, text)
    
    async def close(self):
        await self.http.aclose()


# ============================================================
# FACTORY
# ============================================================

def create_watcher(cdp_url: str = "http://127.0.0.1:19222",
                   chat_api_url: str = "http://127.0.0.1:8250") -> PlatformWatcher:
    """Create a PlatformWatcher with a CloakCDP client."""
    cdp = CloakCDP(cdp_url)
    return PlatformWatcher(cdp, chat_api_url)