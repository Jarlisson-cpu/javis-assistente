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


def test_chat_ai_plugin_does_not_answer_open_app_commands(monkeypatch) -> None:
    event_bus = EventBus()
    plugin = ChatAIPlugin()
    plugin.setup(event_bus)
    responses = []
    event_bus.subscribe("system_message", lambda event: responses.append(event.payload.get("text")))
    monkeypatch.setattr(plugin._ai_manager, "get_response", lambda text: "resposta indevida")

    event_bus.publish_sync(
        Event(name="user_message", payload={"text": "abra o Chrome"}, source="voice")
    )

    assert responses == []


def test_chat_ai_plugin_does_not_answer_agent_command_without_task(monkeypatch) -> None:
    event_bus = EventBus()
    plugin = ChatAIPlugin()
    plugin.setup(event_bus)
    responses = []
    event_bus.subscribe("system_message", lambda event: responses.append(event.payload.get("text")))
    monkeypatch.setattr(plugin._ai_manager, "get_response", lambda text: "resposta indevida")

    event_bus.publish_sync(Event(name="user_message", payload={"text": "planejar"}, source="web"))

    assert responses == []
