import time

import pytest

from core.event_bus import Event, EventBus
from memory.notes import NotesStore
from plugins.productivity import ProductivityPlugin, calculate
from skills import SkillExecutor, SkillRegistry
from skills.router import SkillRouter
from users import UserStore
from users import context as user_context


class AllowAll:
    def is_allowed(self, key):
        return True


@pytest.mark.parametrize(
    ("expression", "expected"),
    [
        ("15 vezes 3", "45"),
        ("dois mais dois", "4"),
        ("100 dividido por 8", "12,5"),
        ("2 elevado a 10", "1.024"),
        ("vinte por cento de 150", "30"),
        ("3,5 mais 1,25", "4,75"),
    ],
)
def test_calculator_understands_spoken_math(expression, expected):
    assert calculate(expression) == expected


def test_calculator_rejects_code():
    with pytest.raises(ValueError):
        calculate("__import__('os').system('dir')")
    with pytest.raises(ValueError):
        calculate("1 dividido por 0")


@pytest.fixture
def assistant(tmp_path):
    registry = SkillRegistry()
    bus = EventBus()
    plugin = ProductivityPlugin(registry=registry, notes=NotesStore(tmp_path / "db.sqlite"))
    plugin.setup(bus)
    SkillRouter(registry, SkillExecutor(AllowAll(), None)).attach(bus)
    replies = []
    bus.subscribe("system_message", lambda e: replies.append(e.payload["text"]))

    async def say(text):
        await bus.publish(Event(name="user_message", payload={"text": text}))
        return replies[-1] if replies else None

    yield say, replies, plugin
    plugin.teardown()
    user_context.set_current_user(None)


@pytest.mark.asyncio
async def test_notes_round_trip(assistant):
    say, *_ = assistant
    assert await say("anota comprar pão e leite") == "Anotado: comprar pão e leite."
    assert await say("anota: ligar para a Maria") == "Anotado: ligar para a Maria."
    assert await say("ler minhas notas") == "Suas notas: 1. comprar pão e leite; 2. ligar para a Maria."


@pytest.mark.asyncio
async def test_timer_fires_reminder(assistant):
    say, replies, _ = assistant
    reply = await say("me lembra em 1 segundo de beber água")
    assert "Te aviso em 1 segundo" in reply
    assert "beber água" in await say("quais são meus lembretes")
    deadline = time.monotonic() + 5
    while replies[-1] != "⏰ Lembrete: beber água." and time.monotonic() < deadline:
        time.sleep(0.05)
    assert replies[-1] == "⏰ Lembrete: beber água."


@pytest.mark.asyncio
async def test_greeting_and_rename_use_current_user(assistant, tmp_path):
    say, _, plugin = assistant
    users = UserStore(tmp_path / "users.sqlite")
    user_context.set_current_user(users.create_user("joao", "senha123", "João"))
    plugin._users = users

    assert "João" in await say("bom dia")
    assert await say("me chama de Chefe") == "Combinado, vou te chamar de Chefe."
    assert "Chefe" in await say("quem sou eu")
