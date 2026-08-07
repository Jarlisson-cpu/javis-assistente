"""Testes para o plugin de chat AI."""

from core.event_bus import Event, EventBus
from plugins.chat_ai.__init__ import ChatAIPlugin


def test_chat_ai_plugin_publishes_system_message_on_user_message() -> None:
    event_bus = EventBus()
    plugin = ChatAIPlugin()
    plugin.setup(event_bus)

    received = []

    def system_message_handler(event: Event) -> None:
        received.append(event.payload.get("text"))

    event_bus.subscribe("system_message", system_message_handler)
    event_bus.publish_sync(Event(name="user_message", payload={"text": "Qual é o seu nome?"}, source="user"))

    assert received, "O plugin deve publicar uma mensagem de sistema"
    assert "Jarvis" in received[0] or "Sou o Jarvis" in received[0]
