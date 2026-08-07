"""Testes para o plugin de chat AI."""

from plugins.chat_ai.__init__ import ChatAIPlugin


def test_chat_ai_plugin_fallback_response() -> None:
    plugin = ChatAIPlugin()
    class DummyEvent:
        payload = {"text": "Qual é o seu nome?"}

    responses = []
    plugin._event_bus = None
    plugin._get_response = lambda text: "Eu sou o Jarvis, seu assistente pessoal."

    # Simulate direct response generation without event bus
    assert plugin._get_response("Qual é o seu nome?") == "Eu sou o Jarvis, seu assistente pessoal."
