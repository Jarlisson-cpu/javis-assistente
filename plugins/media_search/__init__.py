from __future__ import annotations

import asyncio

import security.manager as security_manager
from core.event_bus import Event, EventBus
from core.logger import get_logger
from core.plugin_loader import Plugin
from media.manager import MediaManager

logger = get_logger("plugin.media_search")


class MediaSearchPlugin(Plugin):
    name = "media_search"
    version = "0.1.0"
    description = "Pesquisa música e vídeo no YouTube."

    def __init__(self) -> None:
        self._media = MediaManager()
        self._event_bus: EventBus | None = None

    def setup(self, event_bus: EventBus) -> None:
        self._event_bus = event_bus
        event_bus.subscribe("user_message", self._on_user_message)

    async def _on_user_message(self, event: Event) -> None:
        text = str((event.payload or {}).get("text", "")).strip()
        normalized = text.lower()
        # tocar/pausar/próxima/volume ficam no plugin notebook_control (skills)
        commands = (
            ("buscar música ", "music"),
            ("buscar musica ", "music"),
            ("buscar vídeo ", "video"),
            ("buscar video ", "video"),
        )
        match = next(((prefix, kind) for prefix, kind in commands if normalized.startswith(prefix)), None)
        if match is None:
            return
        if not security_manager.manager or not security_manager.manager.is_allowed("media.search"):
            await self._reply("Busca de mídia bloqueada pela política de permissões.")
            return

        prefix, kind = match
        try:
            opened = await asyncio.to_thread(self._media.search, text[len(prefix) :], kind)
            response = "Busca aberta no navegador." if opened else "Não consegui abrir o navegador."
        except ValueError as exc:
            response = str(exc)
        await self._reply(response)

    async def _reply(self, text: str) -> None:
        if self._event_bus:
            await self._event_bus.publish(
                Event(name="system_message", payload={"text": text}, source="jarvis")
            )