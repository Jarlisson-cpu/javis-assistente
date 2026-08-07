"""Plugin de exemplo — demonstra a interface mínima que um plugin precisa implementar.

Use-o como modelo ao criar plugins reais (ex.: um agente de pesquisa, um
módulo de organização de arquivos, um agente de segurança, etc.).
"""

from __future__ import annotations

from core.event_bus import Event, EventBus
from core.logger import get_logger
from core.plugin_loader import Plugin

logger = get_logger("plugins.example_greeting")


def _reply(event_bus: EventBus, message: str) -> None:
    event_bus.publish_sync(Event(name="system_message", payload={"text": message}, source="jarvis"))


class ExampleGreetingPlugin(Plugin):
    name = "example_greeting"
    version = "0.1.0"
    description = "Responde com uma saudação e orientações simples para o Jarvis."

    def setup(self, event_bus: EventBus) -> None:
        self._event_bus = event_bus
        event_bus.subscribe("user_message", self._on_user_message)

    def _on_user_message(self, event: Event) -> None:
        text = (event.payload.get("text", "") or "").strip()
        if not text:
            return

        normalized = text.lower()
        logger.info("Plugin de exemplo recebeu mensagem: %s", text)

        if any(word in normalized for word in ("olá", "oi", "ola", "bom dia", "boa tarde", "boa noite")):
            _reply(self._event_bus, "Olá! Eu sou o Jarvis. Diga 'buscar ...', 'abrir ...', 'criar arquivo ...' ou 'apagar arquivo ...'.")
        elif "ajuda" in normalized or "o que você faz" in normalized:
            _reply(self._event_bus, "Posso abrir apps, buscar na web, criar/ler/apagar arquivos e gerenciar permissões. Tente um comando como 'buscar python' ou 'abrir chrome'.")
        elif "tudo bem" in normalized or "como você" in normalized:
            _reply(self._event_bus, "Estou bem, obrigado! Pronto para ajudar você com tarefas no seu computador.")
        else:
            # no reply for unrecognized texts; other plugins may handle them
            return
