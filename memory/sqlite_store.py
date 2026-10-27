from __future__ import annotations

import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from core.logger import get_logger

logger = get_logger("memory")


@dataclass
class MessageRecord:
    id: int | None
    timestamp: datetime
    source: str
    text: str
    username: str | None = None


class SQLiteStore:
    def __init__(self, db_path: str | Path = "./jarvis_memory.db") -> None:
        self.db_path = Path(db_path)
        self._lock = threading.Lock()
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    source TEXT NOT NULL,
                    text TEXT NOT NULL
                )
                """
            )
            columns = {row[1] for row in conn.execute("PRAGMA table_info(messages)")}
            if "username" not in columns:
                # migração de bancos criados antes do suporte a usuários
                conn.execute("ALTER TABLE messages ADD COLUMN username TEXT")
            conn.commit()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        return conn

    def add_message(self, source: str, text: str, username: str | None = None) -> MessageRecord:
        ts = datetime.now(timezone.utc).isoformat()
        with self._lock:
            with self._connect() as conn:
                cur = conn.execute(
                    "INSERT INTO messages (timestamp, source, text, username) VALUES (?, ?, ?, ?)",
                    (ts, source, text, username),
                )
                conn.commit()
                rowid = cur.lastrowid
        logger.debug("Mensagem salva no histórico: %s", rowid)
        return MessageRecord(id=rowid, timestamp=datetime.fromisoformat(ts), source=source, text=text, username=username)

    def list_messages(self, limit: int = 100, username: str | None = None) -> Iterable[MessageRecord]:
        query = "SELECT id, timestamp, source, text, username FROM messages"
        args: tuple[object, ...] = ()
        if username:
            query += " WHERE username = ? OR username IS NULL"
            args = (username,)
        query += " ORDER BY id DESC LIMIT ?"
        with self._connect() as conn:
            rows = conn.execute(query, (*args, limit)).fetchall()
        for r in rows:
            yield MessageRecord(id=r[0], timestamp=datetime.fromisoformat(r[1]), source=r[2], text=r[3], username=r[4])

    def clear_messages(self) -> None:
        with self._lock:
            with self._connect() as conn:
                conn.execute("DELETE FROM messages")
                conn.commit()
        logger.info("Histórico de mensagens limpo")
