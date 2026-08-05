"""
browser-use-backed replacement for the selector-based reads/writes in
cdp_integration.py.

Same problem cdp_integration.CloakCDP solved (read/send messages on a Cloak
Browser tab over CDP), different mechanism: instead of hand-coded CSS
selectors per platform (.bubble.is-in .text, message-in span.selectable-text,
...), an LLM (via browser-use) looks at the page and reads/acts on it
directly. Selectors break silently the moment a platform changes its DOM;
the LLM reads what's actually rendered.

Target management (list/create/close tabs) is unchanged -- that part of CDP
was never the brittle part -- so this module delegates it straight through
to a wrapped CloakCDP instance instead of reimplementing it.

Public interface (get_whatsapp_messages, get_telegram_messages,
send_whatsapp_reply, send_telegram_reply, detect_new_messages, send_reply,
list_targets, find_or_create_tab, create_tab, close_tab, close) matches
cdp_integration.CloakCDP exactly, so PlatformWatcher and app.py work
unmodified against either implementation -- see USE_BROWSER_USE in app.py.
"""
import logging
import os
from typing import Literal, Optional

from pydantic import BaseModel

from browser_use import Agent, Browser
from browser_use.browser.events import SwitchTabEvent
from browser_use.llm import ChatOpenAI

from cdp_integration import CloakCDP

logger = logging.getLogger("browser_use_cdp")

# gpt-4.1-mini, not a Claude model: routing Claude-family models through
# OpenRouter's OpenAI-compatible shim hits a structured-output schema bug
# ("output_config.format.schema: For 'integer' type, property 'minimum' is
# not supported") on every step, since browser-use's own step-control
# schema requires structured tool-calling output. Confirmed directly by
# trying anthropic/claude-haiku-4.5 here before switching -- gpt-4.1-mini
# has no such issue and is priced for a poll loop.
DEFAULT_LLM_MODEL = "openai/gpt-4.1-mini"

READ_MAX_STEPS = 4
SEND_MAX_STEPS = 6


class ExtractedMessage(BaseModel):
    text: str
    sender: Literal["self", "client"]


class MessageList(BaseModel):
    messages: list[ExtractedMessage]


class BrowserUseCDP:
    """Drop-in replacement for cdp_integration.CloakCDP."""

    def __init__(self, cdp_url: str = "http://127.0.0.1:19223", llm_model: str = DEFAULT_LLM_MODEL):
        self.cdp_url = cdp_url
        self._cdp = CloakCDP(cdp_url)
        self._llm = ChatOpenAI(
            model=llm_model,
            api_key=os.environ["OPENROUTER_API_KEY"],
            base_url="https://openrouter.ai/api/v1",
        )

    async def close(self):
        await self._cdp.close()

    # ----------------------------------------------------------
    # TARGET MANAGEMENT -- unchanged, delegated straight through
    # ----------------------------------------------------------

    async def list_targets(self) -> list[dict]:
        return await self._cdp.list_targets()

    async def find_or_create_tab(self, url_pattern: str) -> Optional[dict]:
        return await self._cdp.find_or_create_tab(url_pattern)

    async def create_tab(self, url: str) -> Optional[dict]:
        return await self._cdp.create_tab(url)

    async def close_tab(self, target_id: str):
        await self._cdp.close_tab(target_id)

    # ----------------------------------------------------------
    # BROWSER-USE CORE
    # ----------------------------------------------------------

    async def _browser_focused_on(self, target_id: str) -> Browser:
        """Connect to the shared Cloak Browser and force focus onto the
        exact tab the caller means. Required: browser-use's default focus
        after connect() is whichever page target it discovers first, which
        is not necessarily the tab this platform/session was registered
        against -- multiple platforms can have tabs open in the same Cloak
        Browser instance at once. Confirmed live (3 trials): without this,
        focus was wrong 2 out of 3 times."""
        browser = Browser(cdp_url=self.cdp_url)
        await browser.start()
        await browser.event_bus.dispatch(SwitchTabEvent(target_id=target_id))
        return browser

    async def _read_messages(self, target_id: str) -> list[dict]:
        """Read whatever messages are currently visible in the open
        conversation on this tab. Does not navigate or click -- mirrors the
        old selector-based get_*_messages(), which only ever read the
        already-open conversation too. If the tab is sitting on a chat list
        instead of an open conversation, this correctly returns []."""
        browser = await self._browser_focused_on(target_id)
        try:
            agent = Agent(
                task=(
                    "Do not navigate or click anything. Read only the messages "
                    "currently visible in the open conversation on this page, top "
                    "to bottom. For each one, report its exact text and whether it "
                    "was sent by 'self' (this account) or 'client' (the other "
                    "person/bot in the conversation). If no conversation is open "
                    "(e.g. only a chat list is showing), report an empty list."
                ),
                llm=self._llm,
                browser=browser,
                output_model_schema=MessageList,
            )
            result = await agent.run(max_steps=READ_MAX_STEPS)
            structured = result.structured_output
            if structured is None:
                return []
            return [m.model_dump() for m in structured.messages]
        except Exception as e:
            logger.error("browser-use read failed for tab %s: %s", target_id, e)
            return []
        finally:
            await browser.stop()

    async def get_whatsapp_messages(self, target_id: str) -> list[dict]:
        return await self._read_messages(target_id)

    async def get_telegram_messages(self, target_id: str) -> list[dict]:
        return await self._read_messages(target_id)

    async def _send_reply(self, target_id: str, text: str) -> bool:
        browser = await self._browser_focused_on(target_id)
        try:
            agent = Agent(
                task=(
                    "Do not navigate anywhere and do not open a different "
                    "conversation. Find this page's message input box, type the "
                    "following exact text into it, and send it (press Enter or "
                    f"click the send button, whichever applies here): {text!r}"
                ),
                llm=self._llm,
                browser=browser,
            )
            result = await agent.run(max_steps=SEND_MAX_STEPS)
            return bool(result.is_successful())
        except Exception as e:
            logger.error("browser-use send failed for tab %s: %s", target_id, e)
            return False
        finally:
            await browser.stop()

    async def send_whatsapp_reply(self, target_id: str, text: str) -> bool:
        return await self._send_reply(target_id, text)

    async def send_telegram_reply(self, target_id: str, text: str) -> bool:
        return await self._send_reply(target_id, text)

    # ----------------------------------------------------------
    # GENERIC PLATFORM SUPPORT -- same contract as CloakCDP
    # ----------------------------------------------------------

    async def detect_new_messages(self, target_id: str, platform: str, last_known_count: int = 0) -> list:
        if platform in ("whatsapp", "telegram"):
            msgs = await self._read_messages(target_id)
        else:
            browser = await self._browser_focused_on(target_id)
            try:
                agent = Agent(
                    task="Do not navigate or click anything. Report the visible text content of this page.",
                    llm=self._llm,
                    browser=browser,
                )
                result = await agent.run(max_steps=READ_MAX_STEPS)
                return [{"text": result.final_result() or "", "sender": "unknown"}]
            finally:
                await browser.stop()

        client_msgs = [m for m in msgs if m.get("sender") == "client"]
        if len(client_msgs) > last_known_count:
            return client_msgs[last_known_count:]
        return []

    async def send_reply(self, target_id: str, platform: str, text: str) -> bool:
        if platform == "whatsapp":
            return await self.send_whatsapp_reply(target_id, text)
        elif platform == "telegram":
            return await self.send_telegram_reply(target_id, text)
        else:
            logger.warning("No reply handler for platform: %s", platform)
            return False


def create_watcher(cdp_url: str = "http://127.0.0.1:19223", chat_api_url: str = "http://127.0.0.1:8250"):
    """Same factory shape as cdp_integration.create_watcher, backed by
    BrowserUseCDP instead of CloakCDP. PlatformWatcher itself is unchanged --
    it only calls detect_new_messages/send_reply, both matched above."""
    from cdp_integration import PlatformWatcher

    cdp = BrowserUseCDP(cdp_url)
    return PlatformWatcher(cdp, chat_api_url)
