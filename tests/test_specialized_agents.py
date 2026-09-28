import pytest

from core.event_bus import Event, EventBus
from plugins.specialized_agents import SpecializedAgentsPlugin


@pytest.mark.asyncio
async def test_planning_agent_uses_specialized_prompt():
    event_bus = EventBus()
    plugin = SpecializedAgentsPlugin()
    calls = []

    class FakeAIManager:
        def get_response(self, text, context=None):
            calls.append((text, context))
            return "Plano em etapas"

    plugin._ai_manager = FakeAIManager()
    plugin.setup(event_bus)
    responses = []
    event_bus.subscribe("system_message", lambda event: responses.append(event.payload["text"]))

    await event_bus.publish(
        Event(name="user_message", payload={"text": "planejar organizar meus estudos"}, source="web")
    )

    assert calls[0][0] == "organizar meus estudos"
    assert "etapas" in calls[0][1]["system_prompt"].lower()
    assert responses == ["Plano em etapas"]


def test_chat_router_reserves_specialist_commands():
    plugin = SpecializedAgentsPlugin()

    assert plugin.handles("revisar este texto")
    assert plugin.handles("explicar recursão")
    assert not plugin.handles("qual é a previsão do tempo")