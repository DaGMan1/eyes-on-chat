#!/usr/bin/env python3
"""
eyes-on-chat bridge for ROOT.

Polls the portal's agent API for messages assigned to agent_name="root",
invokes `claude -p` headlessly per message (mapping the portal session_id
1:1 to a Claude Code --session-id for conversational continuity), and
posts the reply back.

Full tool access (2026-07-26) -- this is meant to be a real mirror of the
interactive CLI session, not a crippled read-only copy. Safety comes from
model judgment (see SYSTEM_PROMPT below), not a hard tool block: tested
--permission-mode acceptEdits directly and confirmed it lets Edit/Write/Bash
through without hanging (even destructive commands like `rm -rf`), so a tool
restriction here would just be theater. The one thing genuinely off-limits
is --dangerously-skip-permissions/bypassPermissions -- Claude Code itself
refuses that combination when running as root, full stop.
"""
import json
import logging
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request

PORTAL = "http://127.0.0.1:8250"
AGENT_NAME = "root"
ALLOWED_TOOLS = "Read,Grep,Glob,Edit,Write,Bash,WebSearch,Agent"
TRUSTED_DIRS = ["/home", "/var/opt", "/etc"]
# Curated, not exhaustive -- a REAL structural block (Claude Code denies the
# tool call outright, same as it would deny anything not covered by
# acceptEdits) for the handful of patterns that are catastrophic and never
# legitimately needed unattended. Everything else still relies on the
# SYSTEM_PROMPT's judgment call, same as an interactive session's own
# discretion -- this list exists because "ask first" is a soft instruction,
# and these specific patterns are worth a hard floor under that softness.
DISALLOWED_TOOLS = [
    "Bash(rm -rf*)",
    "Bash(git push --force*)",
    "Bash(git push -f*)",
    "Bash(git reset --hard*)",
]
POLL_WAIT = 25  # seconds; server clamps long-poll to 60 max
CLAUDE_TIMEOUT = 240  # seconds

SYSTEM_PROMPT = (
    "You are ROOT, Garry's VP, replying over eyes-on-chat -- a text/voice-friendly "
    "chat channel he often uses while driving. This is a real mirror of your "
    "interactive CLI session on this VPS, not a stripped-down copy: full tool "
    "access, same judgment, same standards.\n\n"
    "Act freely and immediately on anything safe, reversible, or clearly "
    "requested. For anything destructive, hard to reverse, or with real "
    "blast radius (deleting data, force-pushing, touching production configs "
    "other agents depend on, spending money, anything you'd pause on in the "
    "CLI session) -- do NOT just do it. Describe the plan in your reply and "
    "ask for confirmation, then stop; wait for Garry's next message before "
    "proceeding. There is no human watching this process approve tool calls "
    "for you the way there is in an interactive session -- the chat message "
    "itself IS the approval step, so ask there, don't skip it.\n\n"
    "A handful of patterns (rm -rf, git push --force, git reset --hard) are "
    "hard-blocked at the tool level, not just discouraged -- if one of those "
    "gets denied, don't work around it, tell Garry it's blocked and ask if he "
    "wants it unblocked for this specific case.\n\n"
    "Keep replies short: 1-4 sentences unless he explicitly asks for detail "
    "or it's reporting back on a task. No markdown headers, no heavy bullet "
    "dumps, conversational tone."
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("eyes-on-chat-bridge")


def http_json(method, path, payload=None, params=None, timeout=POLL_WAIT + 15):
    url = PORTAL + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        url, data=data, method=method, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def get_next_message():
    return http_json(
        "GET",
        "/api/chat/agent/next",
        params={"agent_name": AGENT_NAME, "mark_read": "true", "wait": POLL_WAIT},
    )


def post_reply(session_id, content):
    return http_json(
        "POST",
        "/api/chat/agent/reply",
        payload={"session_id": session_id, "content": content, "agent_name": AGENT_NAME},
    )


def set_typing(session_id, is_typing):
    """Best-effort: lets the client show a typing indicator during the long
    (up to CLAUDE_TIMEOUT) gap between receiving a message and posting a reply,
    instead of the page looking blank/frozen. Never raises."""
    try:
        http_json(
            "POST",
            "/api/chat/agent/typing",
            payload={"session_id": session_id, "agent_name": "Claude", "is_typing": is_typing},
            timeout=10,
        )
    except Exception as e:
        log.warning("session=%s: typing signal failed: %s", session_id, e)


def _run_claude(session_flag, session_id, prompt):
    cmd = ["claude", "-p", session_flag, session_id, "--tools", ALLOWED_TOOLS]
    for d in TRUSTED_DIRS:
        cmd += ["--add-dir", d]
    cmd += ["--disallowedTools"] + DISALLOWED_TOOLS
    cmd += [
        "--permission-mode", "acceptEdits",
        "--append-system-prompt", SYSTEM_PROMPT,
        "--output-format", "text",
        prompt,
    ]
    return subprocess.run(cmd, capture_output=True, text=True, timeout=CLAUDE_TIMEOUT)


def ask_claude(session_id, prompt):
    # Every portal session_id is a UUID (database.py uses uuid.uuid4()), reused
    # 1:1 as the Claude Code session ID. --resume continues an existing one;
    # a brand new portal session has no Claude session yet, so --resume fails
    # with "No conversation found" and we fall back to --session-id to create it.
    try:
        result = _run_claude("--resume", session_id, prompt)
        if result.returncode != 0 and "No conversation found" in (result.stderr or ""):
            log.info("session=%s: no existing claude session, creating one", session_id)
            result = _run_claude("--session-id", session_id, prompt)
    except subprocess.TimeoutExpired:
        log.error("claude invocation timed out for session %s", session_id)
        return "That took too long to answer -- try rephrasing, or ask me again in a sec."
    if result.returncode != 0:
        log.error("claude invocation failed (%s): %s", result.returncode, result.stderr[-2000:])
        return "Hit an error answering that -- Garry, check the bridge logs when you get a chance."
    return result.stdout.strip() or "(no response)"


def main():
    log.info("eyes-on-chat bridge starting, agent_name=%s, tools=%s", AGENT_NAME, ALLOWED_TOOLS)
    while True:
        try:
            resp = get_next_message()
        except Exception as e:
            log.error("poll failed: %s", e)
            time.sleep(5)
            continue

        msg = resp.get("message")
        if not msg:
            continue  # long-poll returned empty, loop immediately for the next wait

        session_id = msg["session_id"]
        content = msg.get("content", "")
        sender = msg.get("sender", "")
        if sender not in ("client", "user"):
            continue  # skip our own replies and system/handoff notices

        log.info("session=%s sender=%s: %s", session_id, sender, content[:120])
        set_typing(session_id, True)
        reply = ask_claude(session_id, content)
        set_typing(session_id, False)
        try:
            post_reply(session_id, reply)
            log.info("session=%s replied (%d chars)", session_id, len(reply))
        except Exception as e:
            log.error("reply post failed: %s", e)


if __name__ == "__main__":
    main()
