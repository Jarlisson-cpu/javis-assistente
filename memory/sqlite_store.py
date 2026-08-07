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
            conn.commit()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        return conn

    def add_message(self, source: str, text: str) -> MessageRecord:
        ts = datetime.now(timezone.utc).isoformat()
        with self._lock:
            with self._connect() as conn:
                cur = conn.execute("INSERT INTO messages (timestamp, source, text) VALUES (?, ?, ?)", (ts, source, text))
                conn.commit()
                rowid = cur.lastrowid
        logger.debug("Mensagem salva no histórico: %s", rowid)
        return MessageRecord(id=rowid, timestamp=datetime.fromisoformat(ts), source=source, text=text)

    def list_messages(self, limit: int = 100) -> Iterable[MessageRecord]:
        with self._connect() as conn:
            cur = conn.execute("SELECT id, timestamp, source, text FROM messages ORDER BY id DESC LIMIT ?", (limit,))
            rows = cur.fetchall()
        for r in rows:
            yield MessageRecord(id=r[0], timestamp=datetime.fromisoformat(r[1]), source=r[2], text=r[3])

    def clear_messages(self) -> None:
        with self._lock:
            with self._connect() as conn:
                conn.execute("DELETE FROM messages")
                conn.commit()
        logger.info("Histórico de mensagens limpo")
