from __future__ import annotations

import asyncio

import security.manager as security_manager
from communication.manager import CommunicationManager
from core.event_bus import Event, EventBus
from core.logger import get_logger
from core.plugin_loader import Plugin

logger = get_logger("plugin.communication_draft")


class CommunicationDraftPlugin(Plugin):
    name = "communication_draft"
    version = "0.1.0"
    description = "Abre um rascunho de e-mail no cliente local sem enviá-lo."

    def __init__(self) -> None:
        self._communication = CommunicationManager()
        self._event_bus: EventBus | None = None

    def setup(self, event_bus: EventBus) -> None:
        self._event_bus = event_bus
        event_bus.subscribe("user_message", self._on_user_message)

    async def _on_user_message(self, event: Event) -> None:
        text = str((event.payload or {}).get("text", "")).strip()
        prefix = "rascunho email "
        if not text.lower().startswith(prefix):
            return
        if not security_manager.manager or not security_manager.manager.is_allowed("communication.email_draft"):
            await self._reply("Rascunhos de e-mail bloqueados pela política de permissões.")
            return

        parts = text[len(prefix) :].split("|", maxsplit=2)
        if len(parts) != 3:
            await self._reply("Use: rascunho email <destinatário> | <assunto> | <mensagem>")
            return
        recipient, subject, body = (part.strip() for part in parts)
        try:
            opened = await asyncio.to_thread(
                self._communication.open_email_draft, recipient, subject, body
            )
            response = "Rascunho aberto no cliente de e-mail." if opened else "Não consegui abrir um cliente de e-mail."
        except ValueError as exc:
            response = str(exc)
        await self._reply(response)

    async def _reply(self, text: str) -> None:
        if self._event_bus:
            await self._event_bus.publish(
                Event(name="system_message", payload={"text": text}, source="jarvis")
            )