from __future__ import annotations

import asyncio

import security.manager as security_manager
from core.event_bus import Event, EventBus
from core.logger import get_logger
from core.plugin_loader import Plugin
from vision.manager import VisionManager

logger = get_logger("plugin.vision_ocr")


class VisionOCRPlugin(Plugin):
    name = "vision_ocr"
    version = "0.1.0"
    description = "Extrai texto de imagens locais usando OCR."

    def __init__(self) -> None:
        self._vision = VisionManager()
        self._event_bus: EventBus | None = None

    def setup(self, event_bus: EventBus) -> None:
        self._event_bus = event_bus
        event_bus.subscribe("user_message", self._on_user_message)

    async def _on_user_message(self, event: Event) -> None:
        text = str((event.payload or {}).get("text", "")).strip()
        if not text.lower().startswith("ler imagem "):
            return
        if not security_manager.manager or not security_manager.manager.is_allowed("vision.ocr"):
            await self._reply("OCR bloqueado pela política de permissões.")
            return

        image_path = text[len("ler imagem ") :].strip().strip('"')
        try:
            recognized = await asyncio.to_thread(self._vision.extract_text, image_path)
            await self._reply(recognized or "Nenhum texto foi reconhecido na imagem.")
        except Exception as exc:
            logger.info("OCR falhou para %s: %s", image_path, exc)
            await self._reply(f"Não consegui ler essa imagem: {exc}")

    async def _reply(self, text: str) -> None:
        if self._event_bus:
            await self._event_bus.publish(
                Event(name="system_message", payload={"text": text}, source="jarvis")
            )