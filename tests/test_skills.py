import pytest

from core.event_bus import Event, EventBus
from core.exceptions import ConfirmationDenied
from core.text import normalize, parse_number
from skills import Skill, SkillExecutor, SkillRegistry, recover_raw
from skills.router import SkillRouter


def test_normalize_removes_accents_punctuation_and_polite_prefixes():
    assert normalize("Jarvis, por favor ABRA o Chrome!") == "abra o chrome"
    assert normalize("você pode aumentar o volume?") == "aumentar o volume"
    assert normalize("quanto é 3,5 mais 1,5") == "quanto e 3,5 mais 1,5"
    assert normalize("oi jarvis") == "oi jarvis"


def test_parse_number_understands_digits_and_portuguese_words():
    assert parse_number("50") == 50
    assert parse_number("cinquenta") == 50
    assert parse_number("vinte e cinco") == 25
    assert parse_number("80%") == 80
    assert parse_number("banana") is None


def test_recover_raw_keeps_original_case_and_accents():
    assert recover_raw("digite Olá, João!", "ola joao") == "Olá, João!"


def _registry_with(skill: Skill) -> SkillRegistry:
    registry = SkillRegistry()
    registry.register(skill)
    return registry


def test_registry_matches_first_skill_and_extracts_params():
    registry = _registry_with(
        Skill(name="eco", description="", patterns=[r"repete (?P<texto>.+)"], handler=lambda p: p["texto"], raw_params=["texto"])
    )
    skill, params = registry.match("Jarvis, repete Olá Mundo")
    assert skill.name == "eco"
    assert params == {"texto": "Olá Mundo"}
    assert registry.match("outra coisa") is None


def test_tool_schema_is_valid_json_schema():
    skill = Skill(name="a.b", description="d", handler=lambda p: "", parameters={"x": "X"}, required=["x"])
    assert skill.tool_name == "a_b"
    assert skill.tool_schema() == {
        "type": "object",
        "properties": {"x": {"type": "string", "description": "X"}},
        "required": ["x"],
        "additionalProperties": False,
    }


class DenyAll:
    def is_allowed(self, key):
        return False


class AllowAll:
    def is_allowed(self, key):
        return True


class Confirm:
    def __init__(self, answer):
        self.answer = answer
        self.actions = []

    async def confirm(self, action):
        self.actions.append(action)
        if not self.answer:
            raise ConfirmationDenied(action.key)


@pytest.mark.asyncio
async def test_executor_blocks_without_permission():
    calls = []
    skill = Skill(name="x", description="", handler=lambda p: calls.append(1) or "ok", permission="system.shutdown")
    result = await SkillExecutor(DenyAll(), None).execute(skill, {})
    assert "bloqueada" in result
    assert calls == []


@pytest.mark.asyncio
async def test_executor_requires_confirmation_for_destructive_skill():
    calls = []
    skill = Skill(
        name="x",
        description="",
        handler=lambda p: calls.append(1) or "desligando",
        confirm_key="system.shutdown",
        confirm_text=lambda p: f"Desligar em {p.get('m')}",
    )
    denied = Confirm(False)
    assert await SkillExecutor(AllowAll(), denied).execute(skill, {"m": "5"}) == "Tudo bem, cancelei."
    assert calls == []
    assert denied.actions[0].description == "Desligar em 5"

    assert await SkillExecutor(AllowAll(), Confirm(True)).execute(skill, {}) == "desligando"
    assert calls == [1]


@pytest.mark.asyncio
async def test_executor_reports_handler_errors_and_missing_params():
    def boom(params):
        raise ValueError("Diga um valor entre 0 e 100.")

    skill = Skill(name="x", description="", handler=boom, required=["v"])
    executor = SkillExecutor(AllowAll(), None)
    assert await executor.execute(skill, {}) == "Faltou informar: v."
    assert await executor.execute(skill, {"v": "1"}) == "Diga um valor entre 0 e 100."


@pytest.mark.asyncio
async def test_router_publishes_skill_reply():
    registry = _registry_with(Skill(name="hora", description="", patterns=["que horas sao"], handler=lambda p: "10:00"))
    bus = EventBus()
    SkillRouter(registry, SkillExecutor(AllowAll(), None)).attach(bus)
    replies = []
    bus.subscribe("system_message", lambda e: replies.append(e.payload["text"]))

    await bus.publish(Event(name="user_message", payload={"text": "Que horas são?"}))
    await bus.publish(Event(name="user_message", payload={"text": "nada a ver"}))

    assert replies == ["10:00"]


@pytest.mark.asyncio
async def test_event_bus_isolates_failing_handler():
    bus = EventBus()
    received = []

    def broken(event):
        raise RuntimeError("plugin com defeito")

    bus.subscribe("ping", broken)
    bus.subscribe("ping", lambda e: received.append(e.name))
    await bus.publish(Event(name="ping"))

    assert received == ["ping"]
