"""Notas rápidas ditadas ao JARVIS, guardadas no mesmo SQLite da memória."""

from __future__ import annotations

import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass
class Note:
    id: int
    created_at: datetime
    username: str | None
    text: str


class NotesStore:
    def __init__(self, db_path: str | Path = "jarvis_memory.db") -> None:
        self.db_path = Path(db_path)
        self._lock = threading.Lock()
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS notes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    username TEXT,
                    text TEXT NOT NULL
                )
                """
            )

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(str(self.db_path), check_same_thread=False)

    def add(self, text: str, username: str | None = None) -> Note:
        created = datetime.now(timezone.utc)
        with self._lock, self._connect() as conn:
            cursor = conn.execute(
                "INSERT INTO notes (created_at, username, text) VALUES (?, ?, ?)",
                (created.isoformat(), username, text),
            )
            note_id = int(cursor.lastrowid or 0)
        return Note(id=note_id, created_at=created, username=username, text=text)

    def list(self, username: str | None = None, limit: int = 20) -> list[Note]:
        query = "SELECT id, created_at, username, text FROM notes"
        args: tuple[object, ...] = ()
        if username:
            query += " WHERE username = ? OR username IS NULL"
            args = (username,)
        query += " ORDER BY id DESC LIMIT ?"
        with self._connect() as conn:
            rows = conn.execute(query, (*args, limit)).fetchall()
        return [Note(id=r[0], created_at=datetime.fromisoformat(r[1]), username=r[2], text=r[3]) for r in rows]

    def clear(self, username: str | None = None) -> int:
        with self._lock, self._connect() as conn:
            if username:
                cursor = conn.execute("DELETE FROM notes WHERE username = ? OR username IS NULL", (username,))
            else:
                cursor = conn.execute("DELETE FROM notes")
            return cursor.rowcount
