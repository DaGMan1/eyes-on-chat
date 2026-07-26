"""
LeLinc/CoSidekick Unified Chat — Database Module

SQLite backend (SQLCipher-ready). All message storage.
"""
import sqlite3
import json
import os
import uuid
from datetime import datetime, timezone

DB_PATH = os.path.join(os.path.dirname(__file__), "chat.db")

# ============================================================
# SCHEMA
# ============================================================

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    client_name TEXT NOT NULL,
    client_email TEXT NOT NULL,
    business_name TEXT DEFAULT '',
    product TEXT NOT NULL DEFAULT 'kvd',
    agent_profile TEXT DEFAULT 'cosidekick',
    status TEXT DEFAULT 'active',
    qr_code TEXT DEFAULT '',
    created_at TIMESTAMP DEFAULT (datetime('now')),
    updated_at TIMESTAMP DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    platform TEXT NOT NULL DEFAULT 'webchat',
    platform_message_id TEXT DEFAULT '',
    sender TEXT NOT NULL,
    sender_name TEXT DEFAULT '',
    content TEXT NOT NULL,
    message_type TEXT DEFAULT 'text',
    metadata TEXT DEFAULT '{}',
    read BOOLEAN DEFAULT 0,
    created_at TIMESTAMP DEFAULT (datetime('now')),
    FOREIGN KEY (session_id) REFERENCES sessions(id)
);

CREATE TABLE IF NOT EXISTS platform_connections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    platform TEXT NOT NULL,
    tab_id TEXT DEFAULT '',
    status TEXT DEFAULT 'active',
    last_heartbeat TIMESTAMP,
    created_at TIMESTAMP DEFAULT (datetime('now')),
    FOREIGN KEY (session_id) REFERENCES sessions(id)
);

CREATE TABLE IF NOT EXISTS agent_assignments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    agent_name TEXT NOT NULL,
    role TEXT DEFAULT 'primary',
    is_active BOOLEAN DEFAULT 1,
    assigned_at TIMESTAMP DEFAULT (datetime('now')),
    FOREIGN KEY (session_id) REFERENCES sessions(id)
);

CREATE TABLE IF NOT EXISTS push_subscriptions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    endpoint TEXT NOT NULL UNIQUE,
    p256dh TEXT NOT NULL,
    auth TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT (datetime('now')),
    FOREIGN KEY (session_id) REFERENCES sessions(id)
);

CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id);
CREATE INDEX IF NOT EXISTS idx_messages_created ON messages(created_at);
CREATE INDEX IF NOT EXISTS idx_push_subs_session ON push_subscriptions(session_id);
CREATE INDEX IF NOT EXISTS idx_sessions_status ON sessions(status);
"""


# ============================================================
# CONNECTION
# ============================================================

_schema_initialized = False


def get_conn():
    """Get a database connection. Creates the schema on first call only --
    re-running executescript() on every single connection (as before) was
    harmless but wasteful at this call volume."""
    global _schema_initialized
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    if not _schema_initialized:
        conn.executescript(SCHEMA_SQL)
        conn.commit()
        _schema_initialized = True
    return conn


# ============================================================
# SESSION OPERATIONS
# ============================================================

def create_session(client_name, client_email, business_name="", product="kvd"):
    """Create a new chat session. Returns session dict."""
    sid = str(uuid.uuid4())
    conn = get_conn()
    conn.execute(
        "INSERT INTO sessions (id, client_name, client_email, business_name, product) VALUES (?, ?, ?, ?, ?)",
        (sid, client_name, client_email, business_name, product)
    )
    # Assign default agent
    conn.execute(
        "INSERT INTO agent_assignments (session_id, agent_name, role) VALUES (?, 'cosidekick', 'primary')",
        (sid,)
    )
    conn.commit()
    row = conn.execute("SELECT * FROM sessions WHERE id=?", (sid,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_session(session_id):
    """Get session by ID."""
    conn = get_conn()
    row = conn.execute("SELECT * FROM sessions WHERE id=?", (session_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def list_active_sessions(product=None):
    """List all active sessions."""
    conn = get_conn()
    if product:
        rows = conn.execute(
            "SELECT * FROM sessions WHERE status='active' AND product=? ORDER BY updated_at DESC",
            (product,)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM sessions WHERE status='active' ORDER BY updated_at DESC"
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def update_session_status(session_id, status):
    """Archive/close a session."""
    conn = get_conn()
    conn.execute(
        "UPDATE sessions SET status=?, updated_at=datetime('now') WHERE id=?",
        (status, session_id)
    )
    conn.commit()
    conn.close()


# ============================================================
# MESSAGE OPERATIONS
# ============================================================

def add_message(session_id, platform, sender, sender_name, content,
                message_type="text", platform_message_id="", metadata=None):
    """Add a message to a session. Returns message dict."""
    conn = get_conn()
    conn.execute(
        """INSERT INTO messages (session_id, platform, sender, sender_name, 
           content, message_type, platform_message_id, metadata)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (session_id, platform, sender, sender_name, content,
         message_type, platform_message_id,
         json.dumps(metadata or {}))
    )
    # Update session timestamp
    conn.execute(
        "UPDATE sessions SET updated_at=datetime('now') WHERE id=?",
        (session_id,)
    )
    conn.commit()
    msg_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    row = conn.execute("SELECT * FROM messages WHERE id=?", (msg_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_messages(session_id, limit=50, offset=0):
    """Get message history for a session."""
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM messages WHERE session_id=? ORDER BY created_at DESC LIMIT ? OFFSET ?",
        (session_id, limit, offset)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_unread_messages(session_id=None, agent_name=None):
    """Get unread messages, optionally filtered by session or agent."""
    conn = get_conn()
    if session_id:
        rows = conn.execute(
            "SELECT * FROM messages WHERE session_id=? AND read=0 ORDER BY created_at ASC",
            (session_id,)
        ).fetchall()
    elif agent_name:
        # Get messages from sessions assigned to this agent
        rows = conn.execute(
            """SELECT m.* FROM messages m
               JOIN agent_assignments a ON m.session_id = a.session_id
               WHERE a.agent_name=? AND a.is_active=1 AND m.read=0
               ORDER BY m.created_at ASC""",
            (agent_name,)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM messages WHERE read=0 ORDER BY created_at ASC"
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def mark_read(session_id, message_ids):
    """Mark messages as read."""
    if not message_ids:
        return
    conn = get_conn()
    placeholders = ",".join("?" for _ in message_ids)
    conn.execute(
        f"UPDATE messages SET read=1 WHERE session_id=? AND id IN ({placeholders})",
        (session_id, *message_ids)
    )
    conn.commit()
    conn.close()


def get_latest_message(session_id):
    """Get the most recent message in a session."""
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM messages WHERE session_id=? ORDER BY created_at DESC LIMIT 1",
        (session_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


# ============================================================
# AGENT ASSIGNMENT
# ============================================================

def assign_agent(session_id, agent_name, role="primary"):
    """Assign an agent to a session. Deactivates current primary if role=primary."""
    conn = get_conn()
    if role == "primary":
        conn.execute(
            "UPDATE agent_assignments SET is_active=0 WHERE session_id=? AND role='primary'",
            (session_id,)
        )
    conn.execute(
        "INSERT INTO agent_assignments (session_id, agent_name, role) VALUES (?, ?, ?)",
        (session_id, agent_name, role)
    )
    conn.commit()
    conn.close()


def get_current_agent(session_id):
    """Get the currently active agent for a session."""
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM agent_assignments WHERE session_id=? AND is_active=1 ORDER BY assigned_at DESC LIMIT 1",
        (session_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


# ============================================================
# PUSH SUBSCRIPTIONS (Web Push, for the PWA)
# ============================================================

def add_push_subscription(session_id, endpoint, p256dh, auth):
    """Store (or refresh) a browser's push subscription for a session."""
    conn = get_conn()
    conn.execute(
        """INSERT INTO push_subscriptions (session_id, endpoint, p256dh, auth)
           VALUES (?, ?, ?, ?)
           ON CONFLICT(endpoint) DO UPDATE SET session_id=excluded.session_id,
               p256dh=excluded.p256dh, auth=excluded.auth""",
        (session_id, endpoint, p256dh, auth)
    )
    conn.commit()
    conn.close()


def get_push_subscriptions(session_id):
    """All push subscriptions registered for a session (usually one per device)."""
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM push_subscriptions WHERE session_id=?", (session_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def remove_push_subscription(endpoint):
    """Drop a subscription that the push service reports as expired/invalid."""
    conn = get_conn()
    conn.execute("DELETE FROM push_subscriptions WHERE endpoint=?", (endpoint,))
    conn.commit()
    conn.close()


# ============================================================
# PLATFORM CONNECTIONS
# ============================================================

def add_connection(session_id, platform, tab_id=""):
    """Track a Cloak browser tab for a platform."""
    conn = get_conn()
    conn.execute(
        "INSERT INTO platform_connections (session_id, platform, tab_id) VALUES (?, ?, ?)",
        (session_id, platform, tab_id)
    )
    conn.commit()
    conn.close()


def update_connection_tab(session_id, platform, tab_id):
    """Update the tab ID for a connection."""
    conn = get_conn()
    conn.execute(
        "UPDATE platform_connections SET tab_id=?, last_heartbeat=datetime('now') WHERE session_id=? AND platform=?",
        (tab_id, session_id, platform)
    )
    conn.commit()
    conn.close()


def list_connections():
    """All platform connections, most recently active first."""
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM platform_connections ORDER BY last_heartbeat DESC, created_at DESC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ============================================================
# QR CODE DATA
# ============================================================

def generate_qr_data(session_id, platform="webchat"):
    """Generate the data to encode in a QR code for a session."""
    # chat.keyview.com.au has no DNS record (dead domain) -- hub.keyview.com.au
    # is the real, working, Basic-Auth-gated host this is actually served from.
    base_url = "https://hub.keyview.com.au"
    if platform == "whatsapp":
        # WhatsApp wa.me link — number TBD
        return f"https://wa.me/614XXXXXXXX?text=Hi%2C%20I%27d%20like%20to%20chat"
    elif platform == "telegram":
        # Telegram t.me link — bot username TBD
        return f"https://t.me/CoSidekickBot?start={session_id}"
    else:
        # Our web chat
        return f"{base_url}/chat/{session_id}"


# ============================================================
# INIT
# ============================================================

def init_db():
    """Initialize the database (idempotent)."""
    conn = get_conn()
    conn.close()
    return True