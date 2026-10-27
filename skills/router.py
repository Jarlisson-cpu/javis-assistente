"""Roteia `user_message` para a skill cujo padrão casar com o texto."""

from __future__ import annotations

from typing import Any

from core.event_bus import Event, EventBus
from core.logger import get_logger
from skills import SkillExecutor, SkillRegistry

logger = get_logger("skills.router")


class SkillRouter:
    def __init__(self, registry: SkillRegistry, executor: SkillExecutor) -> None:
        self.registry = registry
        self.executor = executor
        self._event_bus: EventBus | None = None

    def attach(self, event_bus: EventBus) -> None:
        self._event_bus = event_bus
        event_bus.subscribe("user_message", self.on_user_message)

    async def on_user_message(self, event: Event) -> None:
        payload: dict[str, Any] = event.payload or {}
        text = str(payload.get("text") or "").strip()
        if not text:
            return
        found = self.registry.match(text)
        if found is None:
            return
        skill, params = found
        logger.info("Comando reconhecido: %s %s", skill.name, params)
        response = await self.executor.execute(skill, params)
        if self._event_bus is not None and response:
            await self._event_bus.publish(
                Event(name="system_message", payload={"text": response, "skill": skill.name}, source="jarvis")
            )
