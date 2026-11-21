"""SQLite storage. Plain sqlite3 (stdlib); callers run these methods in a worker
thread via asyncio.to_thread so the event loop is never blocked."""
import json
import os
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone

SCHEMA = """
CREATE TABLE IF NOT EXISTS messages (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    role       TEXT NOT NULL,          -- 'user' or 'assistant'
    content    TEXT NOT NULL,
    metadata   TEXT,                   -- JSON string, assistant messages only
    created_at TEXT NOT NULL           -- server time, ISO-8601
);
CREATE INDEX IF NOT EXISTS idx_messages_session_id ON messages(session_id, id);
CREATE TABLE IF NOT EXISTS sessions (
    session_id    TEXT PRIMARY KEY,
    system_prompt TEXT,                -- kept here, NEVER in messages
    created_at    TEXT NOT NULL
);
"""


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def path_from_url(database_url: str) -> str:
    """sqlite:////data/app.db -> /data/app.db ; sqlite:///./x.db -> ./x.db"""
    prefix = "sqlite:///"
    if not database_url.startswith(prefix):
        raise ValueError("DATABASE_URL must start with sqlite:///")
    return database_url[len(prefix):]


@dataclass
class SessionData:
    system_prompt: str | None
    history: list[dict]  # [{"role":..., "content":...}] oldest first


class Database:
    def __init__(self, database_url: str):
        self.path = path_from_url(database_url)

    def _connect(self) -> sqlite3.Connection:
        # isolation_level=None -> autocommit; we issue BEGIN/COMMIT explicitly.
        conn = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        conn.execute("PRAGMA busy_timeout=10000")
        return conn

    def init(self) -> None:
        directory = os.path.dirname(os.path.abspath(self.path))
        os.makedirs(directory, exist_ok=True)
        with closing(self._connect()) as conn:
            conn.execute("PRAGMA journal_mode=WAL")  # persists in the db file
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.executescript(SCHEMA)

    def ping(self) -> bool:
        with closing(self._connect()) as conn:
            conn.execute("SELECT 1 FROM messages LIMIT 1").fetchall()
        return True

    def load_session(self, session_id: str) -> SessionData | None:
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT system_prompt FROM sessions WHERE session_id = ?", (session_id,)
            ).fetchone()
            if row is None:
                return None
            rows = conn.execute(
                "SELECT role, content FROM messages WHERE session_id = ? ORDER BY id", (session_id,)
            ).fetchall()
        return SessionData(row[0], [{"role": r, "content": c} for r, c in rows])

    def get_history(self, session_id: str) -> list[dict] | None:
        """Public history shape. None if the session is unknown. No system prompt."""
        with closing(self._connect()) as conn:
            if conn.execute("SELECT 1 FROM sessions WHERE session_id = ?", (session_id,)).fetchone() is None:
                return None
            rows = conn.execute(
                "SELECT role, content, metadata, created_at FROM messages WHERE session_id = ? ORDER BY id",
                (session_id,),
            ).fetchall()
        out = []
        for role, content, metadata, created_at in rows:
            item = {"role": role, "content": content, "created_at": created_at}
            if metadata is not None:
                item["metadata"] = json.loads(metadata)
            out.append(item)
        return out

    def save_exchange(
        self,
        session_id: str,
        system_prompt: str | None,
        user_content: str,
        user_ts: str,
        assistant_content: str,
        metadata: dict,
        assistant_ts: str,
    ) -> None:
        """Persist user + assistant message (and create/update the session) atomically."""
        meta_json = json.dumps(metadata)
        with closing(self._connect()) as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                conn.execute(
                    "INSERT INTO sessions(session_id, system_prompt, created_at) VALUES (?, ?, ?) "
                    "ON CONFLICT(session_id) DO UPDATE SET "
                    "system_prompt = COALESCE(excluded.system_prompt, sessions.system_prompt)",
                    (session_id, system_prompt, user_ts),
                )
                conn.execute(
                    "INSERT INTO messages(session_id, role, content, metadata, created_at) VALUES (?, 'user', ?, NULL, ?)",
                    (session_id, user_content, user_ts),
                )
                conn.execute(
                    "INSERT INTO messages(session_id, role, content, metadata, created_at) VALUES (?, 'assistant', ?, ?, ?)",
                    (session_id, assistant_content, meta_json, assistant_ts),
                )
                conn.execute("COMMIT")
            except BaseException:
                conn.execute("ROLLBACK")
                raise
