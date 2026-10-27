"""Sobe o JarvisCore completo (todos os plugins) com banco e config temporários."""

import asyncio

import pytest

from core.app import JarvisCore
from core.event_bus import Event
from users import context as user_context


@pytest.fixture
def core(tmp_path, monkeypatch):
    for key in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GOOGLE_API_KEY", "JARVIS_AI_PROVIDER"):
        monkeypatch.delenv(key, raising=False)
    db = (tmp_path / "jarvis.db").as_posix()
    config = tmp_path / "config.yaml"
    config.write_text(
        f"""
logging:
  directory: "{(tmp_path / 'logs').as_posix()}"
  console_output: false
memory:
  db_path: "{db}"
security:
  permissions_file: "{(tmp_path / 'perms.json').as_posix()}"
  require_confirmation_for: [notes.clear]
voice:
  enable_tts: false
""",
        encoding="utf-8",
    )
    instance = JarvisCore(config_path=str(config))
    instance.bootstrap()
    yield instance
    instance.shutdown()
    user_context.set_current_user(None)


async def talk(core, text):
    replies = []
    handler = lambda event: replies.append(event.payload["text"])  # noqa: E731
    core.event_bus.subscribe("system_message", handler)
    await core.event_bus.publish(Event(name="user_message", payload={"text": text}, source="terminal"))
    core.event_bus.unsubscribe("system_message", handler)
    return replies


@pytest.mark.asyncio
async def test_core_answers_once_per_command(core):
    assert len(await talk(core, "que horas são")) == 1
    assert len(await talk(core, "qual é o seu nome?")) == 1
    replies = await talk(core, "anota testar o jarvis")
    assert replies == ["Anotado: testar o jarvis."]


@pytest.mark.asyncio
async def test_core_users_and_default_local_user(core):
    assert core.default_local_user() is None
    core.users.create_user("ana", "senha123", "Ana", role="admin")
    user = core.default_local_user()
    assert user.username == "ana"
    core.login("ana")
    assert core.current_user.display_name == "Ana"
    assert "Ana" in (await talk(core, "oi"))[0]


@pytest.mark.asyncio
async def test_core_persists_history_with_username(core):
    core.users.create_user("bia", "senha123")
    core.login("bia")
    await talk(core, "que dia é hoje")
    await asyncio.sleep(0.3)  # persistência roda em thread
    records = list(core.memory.list_messages(limit=5))
    assert {r.username for r in records} == {"bia"}
    assert [r.source for r in records] == ["jarvis", "terminal"]  # mais recente primeiro: pergunta antes da resposta


@pytest.mark.asyncio
async def test_unknown_command_without_ai_suggests_closest(core):
    replies = await talk(core, "aumenta o volum")
    assert replies and "aumentar o volume" in replies[0]
