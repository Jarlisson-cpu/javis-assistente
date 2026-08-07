"""Plugin de chat genérico para responder perguntas em estilo assistente."""

from __future__ import annotations

import logging
from core.event_bus import Event, EventBus
from core.logger import get_logger
from core.plugin_loader import Plugin
from ai import AIManager

logger = get_logger("plugin.chat_ai")


class ChatAIPlugin(Plugin):
    name = "chat_ai"
    version = "0.1.0"
    description = "Responde perguntas de conversa como um assistente de IA."

    def __init__(self) -> None:
        self._ai_manager = AIManager()
        self._event_bus: EventBus | None = None

    def setup(self, event_bus: EventBus) -> None:
        self._event_bus = event_bus
        event_bus.subscribe("user_message", self._on_user_message)

    async def _on_user_message(self, event: Event) -> None:
        payload = event.payload or {}
        text = (payload.get("text") or "").strip()
        if not text:
            return

        normalized = text.lower()
        if self._is_command(normalized):
            return

        response = self._ai_manager.get_response(text)
        if self._event_bus is not None:
            await self._event_bus.publish(Event(name="system_message", payload={"text": response}, source="jarvis"))

    def _is_command(self, normalized: str) -> bool:
        command_prefixes = (
            "buscar ",
            "abrir ",
            "abre ",
            "abra ",
            "criar arquivo ",
            "ler arquivo ",
            "apagar arquivo ",
        )
        if any(normalized.startswith(prefix) for prefix in command_prefixes):
            return True

        if any(keyword in normalized for keyword in ("permissão", "permissões", "política", "senha")):
            return True

        return False
