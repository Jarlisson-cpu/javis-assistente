"""Contas de usuário do JARVIS.

Senhas nunca são guardadas em texto: usamos PBKDF2-HMAC-SHA256 com sal
aleatório por usuário e comparação em tempo constante.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import secrets
import sqlite3
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PBKDF2_ITERATIONS = 310_000
USERNAME_PATTERN = re.compile(r"^[a-z0-9_.-]{3,32}$")
MIN_PASSWORD_LENGTH = 6
ROLES = ("admin", "user")


class UserError(ValueError):
    """Erro de validação ou de credenciais."""


@dataclass
class User:
    id: int
    username: str
    display_name: str
    role: str
    created_at: datetime
    preferences: dict[str, Any] = field(default_factory=dict)

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "username": self.username,
            "display_name": self.display_name,
            "role": self.role,
            "created_at": self.created_at.isoformat(),
        }


def hash_password(password: str, *, salt: bytes | None = None, iterations: int = PBKDF2_ITERATIONS) -> str:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return f"pbkdf2_sha256${iterations}${salt.hex()}${digest.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, iterations, salt_hex, digest_hex = encoded.split("$")
    except ValueError:
        return False
    if algorithm != "pbkdf2_sha256":
        return False
    candidate = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), int(iterations))
    return hmac.compare_digest(candidate.hex(), digest_hex)


_DUMMY_HASH: str | None = None


def _dummy_hash() -> str:
    global _DUMMY_HASH
    if _DUMMY_HASH is None:
        _DUMMY_HASH = hash_password(secrets.token_urlsafe(8))
    return _DUMMY_HASH


def normalize_username(username: str) -> str:
    value = (username or "").strip().lower()
    if not USERNAME_PATTERN.fullmatch(value):
        raise UserError("O nome de usuário deve ter de 3 a 32 caracteres: letras, números, ponto, hífen ou _.")
    return value


class UserStore:
    def __init__(self, db_path: str | Path = "jarvis_memory.db") -> None:
        self.db_path = Path(db_path)
        self._lock = threading.Lock()
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL UNIQUE,
                    display_name TEXT NOT NULL,
                    password_hash TEXT NOT NULL,
                    role TEXT NOT NULL DEFAULT 'user',
                    created_at TEXT NOT NULL,
                    preferences TEXT NOT NULL DEFAULT '{}'
                )
                """
            )

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(str(self.db_path), check_same_thread=False)

    @staticmethod
    def _row_to_user(row: tuple[Any, ...]) -> User:
        return User(
            id=row[0],
            username=row[1],
            display_name=row[2],
            role=row[3],
            created_at=datetime.fromisoformat(row[4]),
            preferences=json.loads(row[5] or "{}"),
        )

    _COLUMNS = "id, username, display_name, role, created_at, preferences"

    def count(self) -> int:
        with self._connect() as conn:
            return int(conn.execute("SELECT COUNT(*) FROM users").fetchone()[0])

    def create_user(self, username: str, password: str, display_name: str | None = None, role: str = "user") -> User:
        username = normalize_username(username)
        if len(password) < MIN_PASSWORD_LENGTH:
            raise UserError(f"A senha precisa ter pelo menos {MIN_PASSWORD_LENGTH} caracteres.")
        if role not in ROLES:
            raise UserError(f"Papel inválido: {role}. Use 'admin' ou 'user'.")
        display = (display_name or username).strip()[:64] or username
        created = datetime.now(timezone.utc).isoformat()
        try:
            with self._lock, self._connect() as conn:
                conn.execute(
                    "INSERT INTO users (username, display_name, password_hash, role, created_at) VALUES (?, ?, ?, ?, ?)",
                    (username, display, hash_password(password), role, created),
                )
        except sqlite3.IntegrityError as exc:
            raise UserError(f"O usuário '{username}' já existe.") from exc
        user = self.get(username)
        assert user is not None
        return user

    def get(self, username: str) -> User | None:
        with self._connect() as conn:
            row = conn.execute(
                f"SELECT {self._COLUMNS} FROM users WHERE username = ?", ((username or "").strip().lower(),)
            ).fetchone()
        return self._row_to_user(row) if row else None

    def list(self) -> list[User]:
        with self._connect() as conn:
            rows = conn.execute(f"SELECT {self._COLUMNS} FROM users ORDER BY id").fetchall()
        return [self._row_to_user(row) for row in rows]

    def authenticate(self, username: str, password: str) -> User | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT password_hash FROM users WHERE username = ?", ((username or "").strip().lower(),)
            ).fetchone()
        if row is None:
            # mesmo custo de CPU para usuário inexistente, evitando enumeração por tempo
            verify_password(password, _dummy_hash())
            return None
        if not verify_password(password, row[0]):
            return None
        return self.get(username)

    def set_password(self, username: str, password: str) -> None:
        if len(password) < MIN_PASSWORD_LENGTH:
            raise UserError(f"A senha precisa ter pelo menos {MIN_PASSWORD_LENGTH} caracteres.")
        with self._lock, self._connect() as conn:
            cursor = conn.execute(
                "UPDATE users SET password_hash = ? WHERE username = ?", (hash_password(password), username.lower())
            )
        if cursor.rowcount == 0:
            raise UserError(f"Usuário '{username}' não encontrado.")

    def set_display_name(self, username: str, display_name: str) -> User:
        display = display_name.strip()[:64]
        if not display:
            raise UserError("O nome não pode ficar vazio.")
        with self._lock, self._connect() as conn:
            conn.execute("UPDATE users SET display_name = ? WHERE username = ?", (display, username.lower()))
        user = self.get(username)
        if user is None:
            raise UserError(f"Usuário '{username}' não encontrado.")
        return user

    def update_preferences(self, username: str, **changes: Any) -> User:
        user = self.get(username)
        if user is None:
            raise UserError(f"Usuário '{username}' não encontrado.")
        preferences = {**user.preferences, **changes}
        with self._lock, self._connect() as conn:
            conn.execute(
                "UPDATE users SET preferences = ? WHERE username = ?", (json.dumps(preferences), user.username)
            )
        user.preferences = preferences
        return user

    def delete(self, username: str) -> bool:
        with self._lock, self._connect() as conn:
            cursor = conn.execute("DELETE FROM users WHERE username = ?", (username.strip().lower(),))
        return cursor.rowcount > 0


class SessionManager:
    """Sessões em memória para a interface web (token opaco com expiração)."""

    def __init__(self, ttl_hours: float = 12) -> None:
        self._ttl_seconds = ttl_hours * 3600
        self._sessions: dict[str, tuple[str, float]] = {}
        self._lock = threading.Lock()

    def create(self, username: str) -> str:
        token = secrets.token_urlsafe(32)
        expires = datetime.now(timezone.utc).timestamp() + self._ttl_seconds
        with self._lock:
            self._sessions[token] = (username, expires)
        return token

    def resolve(self, token: str | None) -> str | None:
        if not token:
            return None
        now = datetime.now(timezone.utc).timestamp()
        with self._lock:
            entry = self._sessions.get(token)
            if entry is None:
                return None
            username, expires = entry
            if expires < now:
                del self._sessions[token]
                return None
            return username

    def revoke(self, token: str | None) -> None:
        with self._lock:
            self._sessions.pop(token or "", None)
