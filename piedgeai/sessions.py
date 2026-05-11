"""SQLite-backed conversation state kept outside model memory."""

from __future__ import annotations

from dataclasses import dataclass
import json
import sqlite3
import time
from pathlib import Path
from uuid import uuid4


@dataclass(frozen=True)
class Message:
    """One persisted conversation turn."""

    role: str
    content: str
    created_at: float


class SessionStore:
    """Small SQLite store for durable, model-independent sessions."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    metadata TEXT NOT NULL DEFAULT '{}'
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    FOREIGN KEY(session_id) REFERENCES sessions(id)
                )
                """
            )

    def ensure_session(self, session_id: str | None = None) -> str:
        """Return an existing session id or create a new lightweight session."""

        now = time.time()
        sid = session_id or uuid4().hex
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO sessions(id, created_at, updated_at, metadata)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET updated_at=excluded.updated_at
                """,
                (sid, now, now, "{}"),
            )
        return sid

    def append(self, session_id: str, role: str, content: str) -> None:
        """Append one message to a session."""

        now = time.time()
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO messages(session_id, role, content, created_at) VALUES (?, ?, ?, ?)",
                (session_id, role, content, now),
            )
            conn.execute("UPDATE sessions SET updated_at = ? WHERE id = ?", (now, session_id))

    def history(self, session_id: str, limit: int = 8) -> list[Message]:
        """Fetch recent messages, preserving only compact external context."""

        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT role, content, created_at FROM messages
                WHERE session_id = ? ORDER BY id DESC LIMIT ?
                """,
                (session_id, limit),
            ).fetchall()
        return [Message(*row) for row in reversed(rows)]

    def as_prompt_context(self, session_id: str, limit: int = 6) -> str:
        """Render recent history into a compact prompt prefix."""

        messages = self.history(session_id, limit=limit)
        if not messages:
            return ""
        lines = [f"{message.role}: {message.content}" for message in messages]
        return "\n".join(lines) + "\n"

    def export_session(self, session_id: str) -> dict[str, object]:
        """Return a JSON-serializable session snapshot."""

        return {
            "session_id": session_id,
            "messages": [message.__dict__ for message in self.history(session_id, limit=100)],
        }

    @staticmethod
    def dumps(payload: dict[str, object]) -> str:
        """Compact JSON helper for API responses."""

        return json.dumps(payload, separators=(",", ":"))
