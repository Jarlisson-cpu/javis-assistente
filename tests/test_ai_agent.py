from types import SimpleNamespace

import pytest

import ai
from ai import AnthropicProvider, OpenAIProvider, ToolSpec
from core.event_bus import Event, EventBus
from plugins.chat_ai import ChatAIPlugin
from skills import Skill, SkillRegistry

TOOLS = [ToolSpec(name="volume_aumentar", description="Aumenta o volume", input_schema={"type": "object", "properties": {}})]


def block(**kwargs):
    return SimpleNamespace(**kwargs)


class FakeAnthropicMessages:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    def create(self, **kwargs):
        self.requests.append(kwargs)
        return self.responses.pop(0)


def test_anthropic_provider_runs_tool_loop_and_returns_final_text():
    messages = FakeAnthropicMessages(
        [
            SimpleNamespace(
                stop_reason="tool_use",
                content=[
                    block(type="text", text="Vou aumentar."),
                    block(type="tool_use", id="t1", name="volume_aumentar", input={"percent": "20"}),
                ],
            ),
            SimpleNamespace(stop_reason="end_turn", content=[block(type="text", text="Pronto, aumentei.")]),
        ]
    )
    client = SimpleNamespace(beta=SimpleNamespace(messages=messages))
    calls = []

    reply = AnthropicProvider(client=client).run_with_tools(
        "deixa o som mais alto", TOOLS, lambda name, args: calls.append((name, args)) or "Aumentei 20%.",
        {"user_name": "João", "history": [{"role": "user", "content": "oi"}, {"role": "assistant", "content": "Olá!"}]},
    )

    assert reply == "Pronto, aumentei."
    assert calls == [("volume_aumentar", {"percent": "20"})]
    first = messages.requests[0]
    assert first["model"] == "claude-opus-5-5"
    assert first["tools"][0]["name"] == "volume_aumentar"
    assert "João" in first["system"]
    assert first["messages"][0] == {"role": "user", "content": "oi"}
    second = messages.requests[1]["messages"]
    assert second[-1]["content"] == [{"type": "tool_result", "tool_use_id": "t1", "content": "Aumentei 20%."}]


def test_anthropic_provider_handles_refusal():
    messages = FakeAnthropicMessages([SimpleNamespace(stop_reason="refusal", content=[])])
    client = SimpleNamespace(beta=SimpleNamespace(messages=messages))
    assert "não posso" in AnthropicProvider(client=client).get_response("x")


def test_openai_provider_runs_function_calls():
    responses = [
        SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content=None,
                        tool_calls=[
                            SimpleNamespace(
                                id="c1", function=SimpleNamespace(name="volume_aumentar", arguments='{"percent": "10"}')
                            )
                        ],
                    )
                )
            ]
        ),
        SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="Feito!", tool_calls=None))]),
    ]
    requests = []

    def create(**kwargs):
        requests.append(kwargs)
        return responses.pop(0)

    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    calls = []
    reply = OpenAIProvider(client=client).run_with_tools("mais alto", TOOLS, lambda n, a: calls.append((n, a)) or "ok")

    assert reply == "Feito!"
    assert calls == [("volume_aumentar", {"percent": "10"})]
    assert requests[1]["messages"][-1] == {"role": "tool", "tool_call_id": "c1", "content": "ok"}


def test_pinned_provider_without_key_falls_back_to_configured_one(monkeypatch):
    for key in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GOOGLE_API_KEY", "JARVIS_AI_MODEL"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("JARVIS_AI_PROVIDER", "gemini")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr(ai, "anthropic", SimpleNamespace(Anthropic=lambda: object()))

    manager = ai.AIManager()

    assert manager.provider_name == "anthropic"
    assert manager.model == "claude-opus-5-5"
    assert manager.supports_tools


def test_ai_manager_auto_detects_provider(monkeypatch):
    for key in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GOOGLE_API_KEY", "JARVIS_AI_PROVIDER", "JARVIS_AI_MODEL"):
        monkeypatch.delenv(key, raising=False)
    manager = ai.AIManager()
    assert manager.provider_name == "offline"
    assert manager.is_offline and not manager.supports_tools
    assert "quis dizer 'aumentar o volume'" in manager.get_response("aumenta o volum", {"suggestion": "aumentar o volume"})


@pytest.mark.asyncio
async def test_chat_plugin_lets_agent_execute_skills():
    executed = []
    registry = SkillRegistry()
    registry.register(
        Skill(
            name="tela.print",
            description="Tira um print",
            patterns=["tira um print"],
            handler=lambda p: executed.append("print") or "Print salvo.",
        )
    )

    class FakeAgent:
        supports_tools = True
        is_offline = False

        def run_agent(self, text, tools, call_tool, context):
            assert [t.name for t in tools] == ["tela_print"]
            return f"Feito: {call_tool('tela_print', {})}"

    bus = EventBus()
    plugin = ChatAIPlugin(registry=registry)
    plugin._ai_manager = FakeAgent()
    plugin.setup(bus)
    replies = []
    bus.subscribe("system_message", lambda e: replies.append(e.payload["text"]))

    await bus.publish(Event(name="user_message", payload={"text": "registra minha tela numa imagem"}))
    await bus.publish(Event(name="user_message", payload={"text": "tira um print"}))  # comando direto: o router cuida

    assert executed == ["print"]
    assert replies == ["Feito: Print salvo."]
