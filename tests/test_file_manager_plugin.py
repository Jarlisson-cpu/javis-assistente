import asyncio
from pathlib import Path

import pytest

from core.event_bus import Event, EventBus
from core.exceptions import ConfirmationDenied
from plugins.file_manager import FileManagerPlugin


@pytest.mark.asyncio
async def test_file_manager_read_write(tmp_path: Path, monkeypatch) -> None:
    project_root = tmp_path / "jarvis-assistant"
    project_root.mkdir()
    monkeypatch.chdir(project_root)

    event_bus = EventBus()
    plugin = FileManagerPlugin()
    plugin.setup(event_bus)

    read_messages = []
    event_bus.subscribe("system_message", lambda e: read_messages.append(e.payload.get("text")))

    await event_bus.publish(Event(name="user_message", payload={"text": "criar arquivo test.txt : olá mundo"}))
    await asyncio.sleep(0.05)
    assert (project_root / "test.txt").exists()
    assert any("Arquivo salvo" in msg for msg in read_messages)

    await event_bus.publish(Event(name="user_message", payload={"text": "ler arquivo test.txt"}))
    await asyncio.sleep(0.05)
    assert any("Conteúdo de test.txt" in msg for msg in read_messages)


@pytest.mark.asyncio
async def test_file_manager_delete_requires_confirmation(tmp_path: Path, monkeypatch) -> None:
    project_root = tmp_path / "jarvis-assistant"
    project_root.mkdir()
    monkeypatch.chdir(project_root)
    target = project_root / "test.txt"
    target.write_text("preservar", encoding="utf-8")

    class DenyConfirmation:
        async def confirm(self, action) -> None:
            assert action.key == "file.delete"
            raise ConfirmationDenied(action.key)

    event_bus = EventBus()
    event_bus.confirmation_gate = DenyConfirmation()
    plugin = FileManagerPlugin()
    monkeypatch.setattr("security.manager.manager", None)
    plugin.setup(event_bus)

    await plugin._delete_file("test.txt")

    assert target.exists()
