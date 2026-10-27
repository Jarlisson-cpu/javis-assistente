"""Usuário ativo da sessão local (terminal, voz ou GUI).

A interface web tem sessões próprias por navegador; aqui fica apenas quem está
usando o JARVIS neste computador, para personalizar respostas e separar notas.
"""

from __future__ import annotations

import threading

from users.store import User

_current: User | None = None
_lock = threading.Lock()


def set_current_user(user: User | None) -> None:
    global _current
    with _lock:
        _current = user


def current_user() -> User | None:
    return _current


def display_name(default: str = "") -> str:
    user = _current
    if user is None:
        return default
    return user.display_name or user.username
