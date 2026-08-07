"""Barramento de eventos assíncrono — a espinha dorsal de comunicação entre módulos.

Módulos nunca devem se importar diretamente (ex.: `voice` não importa `ai`).
Em vez disso, publicam e assinam eventos aqui, mantendo baixo acoplamento
entre voice, ai, automation, gui etc.
"""

from __future__ import annotations

import asyncio
import inspect
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from core.logger import get_logger

logger = get_logger("event_bus")

Handler = Callable[["Event"], Any | Awaitable[Any]]


@dataclass
class Event:
    """Evento genérico publicado no barramento."""

    name: str
    payload: dict[str, Any] = field(default_factory=dict)
    source: str | None = None


class EventBus:
    """Barramento pub/sub simples, suportando handlers síncronos e assíncronos."""

    def __init__(self) -> None:
        self._handlers: dict[str, list[Handler]] = defaultdict(list)

    def subscribe(self, event_name: str, handler: Handler) -> None:
        """Registra `handler` para ser chamado quando `event_name` for publicado."""
        self._handlers[event_name].append(handler)
        logger.debug("Handler registrado para evento '%s': %s", event_name, handler)

    def unsubscribe(self, event_name: str, handler: Handler) -> None:
        """Remove um handler previamente registrado."""
        if handler in self._handlers[event_name]:
            self._handlers[event_name].remove(handler)

    async def publish(self, event: Event) -> None:
        """Publica um evento, chamando todos os handlers registrados para ele."""
        handlers = self._handlers.get(event.name, [])
        if not handlers:
            logger.debug("Evento '%s' publicado sem handlers registrados", event.name)
            return

        for handler in handlers:
            result = handler(event)
            if inspect.isawaitable(result):
                await result

    def publish_sync(self, event: Event) -> None:
        """Versão síncrona de `publish`, para chamadas fora de um loop assíncrono."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            asyncio.run(self.publish(event))
            return

        if loop.is_running():
            loop.call_soon_threadsafe(asyncio.create_task, self.publish(event))
        else:
            loop.run_until_complete(self.publish(event))
