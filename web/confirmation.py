"""Confirmação de ações destrutivas pelo navegador.

O pedido que dispara a ação fica aguardando; o painel consulta
`GET /api/confirmations`, mostra a pergunta e responde em
`POST /api/confirmations`.
"""

from __future__ import annotations

import asyncio
import secrets
import threading
from dataclasses import dataclass, field

from core.confirmation import ConfirmationProvider, DestructiveAction


@dataclass
class PendingConfirmation:
    id: str
    action: DestructiveAction
    answered: threading.Event = field(default_factory=threading.Event)
    approved: bool = False


class WebConfirmationProvider(ConfirmationProvider):
    def __init__(self, timeout_seconds: float = 60) -> None:
        self._timeout = timeout_seconds
        self._pending: dict[str, PendingConfirmation] = {}
        self._lock = threading.Lock()

    async def ask(self, action: DestructiveAction) -> bool:
        pending = PendingConfirmation(id=secrets.token_urlsafe(8), action=action)
        with self._lock:
            self._pending[pending.id] = pending
        try:
            answered = await asyncio.to_thread(pending.answered.wait, self._timeout)
            return answered and pending.approved
        finally:
            with self._lock:
                self._pending.pop(pending.id, None)

    def list_pending(self) -> list[dict[str, str]]:
        with self._lock:
            return [
                {"id": item.id, "key": item.action.key, "description": item.action.description}
                for item in self._pending.values()
            ]

    def answer(self, confirmation_id: str, approved: bool) -> bool:
        with self._lock:
            pending = self._pending.get(confirmation_id)
        if pending is None:
            return False
        pending.approved = approved
        pending.answered.set()
        return True
