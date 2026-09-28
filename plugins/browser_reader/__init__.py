from __future__ import annotations

import asyncio

import security.manager as security_manager
from browser.manager import BrowserManager
from core.event_bus import Event, EventBus
from core.logger import get_logger
from core.plugin_loader import Plugin

logger = get_logger("plugin.browser_reader")


class BrowserReaderPlugin(Plugin):
    name = "browser_reader"
    version = "0.1.0"
    description = "Lê texto de uma página pública usando Playwright."

    def __init__(self) -> None:
        self._browser = BrowserManager()
        self._event_bus: EventBus | None = None

    def setup(self, event_bus: EventBus) -> None:
        self._event_bus = event_bus
        event_bus.subscribe("user_message", self._on_user_message)

    async def _on_user_message(self, event: Event) -> None:
        text = str((event.payload or {}).get("text", "")).strip()
        if not text.lower().startswith("ler site "):
            return
        if not security_manager.manager or not security_manager.manager.is_allowed("browser.read"):
            await self._reply("Leitura do navegador bloqueada pela política de permissões.")
            return

        url = text[len("ler site ") :].strip()
        try:
            page_text = await asyncio.to_thread(self._browser.read_page, url)
            await self._reply(page_text or "A página não contém texto legível.")
        except Exception as exc:
            logger.info("Leitura de página falhou: %s", exc)
            await self._reply(f"Não consegui ler essa página: {exc}")

    async def _reply(self, text: str) -> None:
        if self._event_bus:
            await self._event_bus.publish(
                Event(name="system_message", payload={"text": text}, source="jarvis")
            )