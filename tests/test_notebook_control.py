import subprocess

import pytest

from plugins.notebook_control import build_skills
from skills import SkillExecutor, SkillRegistry
from system.controller import SystemController


class FakeMedia:
    def __init__(self):
        self.keys = []

    def control(self, action):
        self.keys.append(action)

    def search(self, query, kind):
        self.keys.append(("search", query, kind))
        return True


class FakeRunner:
    def __init__(self, stdout="", returncode=0):
        self.calls = []
        self.stdout = stdout
        self.returncode = returncode

    def __call__(self, args):
        self.calls.append(list(args))
        return subprocess.CompletedProcess(args, self.returncode, self.stdout, "")


class AllowAll:
    def is_allowed(self, key):
        return True


@pytest.fixture
def setup():
    media, runner, hotkeys, typed = FakeMedia(), FakeRunner(), [], []
    controller = SystemController(
        run=runner, media=media, hotkey=lambda *k: hotkeys.append(k), typer=typed.append
    )
    registry = SkillRegistry()
    for skill in build_skills(controller, media):
        registry.register(skill)

    async def say(text, confirm=True):
        class Gate:
            async def confirm(self, action):
                if not confirm:
                    from core.exceptions import ConfirmationDenied

                    raise ConfirmationDenied(action.key)

        found = registry.match(text)
        assert found is not None, f"nenhuma skill para: {text}"
        skill, params = found
        return await SkillExecutor(AllowAll(), Gate()).execute(skill, params)

    return say, media, runner, hotkeys, typed


@pytest.mark.asyncio
async def test_volume_commands_send_windows_media_keys(setup):
    say, media, *_ = setup
    assert await say("aumenta o volume em 20") == "Aumentei o volume em 20%."
    assert media.keys == ["volume_up"] * 10

    media.keys.clear()
    assert await say("Jarvis, coloca o volume em cinquenta") == "Volume ajustado para 50%."
    assert media.keys == ["volume_down"] * 50 + ["volume_up"] * 25

    media.keys.clear()
    await say("muta o som")
    await say("próxima música")
    await say("pausa a música")
    assert media.keys == ["mute", "next", "play_pause"]


@pytest.mark.asyncio
async def test_shutdown_requires_confirmation_and_supports_delay(setup):
    say, _, runner, *_ = setup
    assert await say("desliga o computador em 30 minutos", confirm=False) == "Tudo bem, cancelei."
    assert runner.calls == []

    reply = await say("desliga o computador em trinta minutos")
    assert runner.calls == [["shutdown", "/s", "/t", "1800"]]
    assert "30 minuto" in reply

    await say("cancela o desligamento")
    assert runner.calls[-1] == ["shutdown", "/a"]


@pytest.mark.asyncio
async def test_shortcuts_keys_and_typing(setup):
    say, _, _, hotkeys, typed = setup
    await say("copia")
    await say("abre uma nova aba")
    await say("minimiza tudo")
    await say("aperta a tecla tab 3 vezes")
    await say("digite Olá, João!")
    assert hotkeys == [("ctrl", "c"), ("ctrl", "t"), ("win", "d"), ("tab",), ("tab",), ("tab",)]
    assert typed == ["Olá, João!"]


@pytest.mark.asyncio
async def test_close_app_uses_polite_taskkill(setup):
    say, _, runner, *_ = setup
    reply = await say("fecha o chrome")
    assert runner.calls == [["taskkill", "/IM", "chrome.exe", "/T"]]
    assert "chrome" in reply


@pytest.mark.asyncio
async def test_brightness_reads_and_sets_with_wmi(setup):
    say, _, runner, *_ = setup
    runner.stdout = "40"
    assert await say("aumenta o brilho") == "Brilho ajustado para 60%."
    assert "WmiSetBrightness" in runner.calls[-1][-1]
    assert "Brightness=60" in runner.calls[-1][-1]


def test_create_folder_stays_inside_known_location(tmp_path, monkeypatch):
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    (tmp_path / "Desktop").mkdir()
    controller = SystemController(run=FakeRunner(), media=FakeMedia())

    assert "Projetos" in controller.create_folder("Projetos", "area de trabalho")
    assert (tmp_path / "Desktop" / "Projetos").is_dir()
    with pytest.raises(ValueError):
        controller.create_folder("..\\fora", "documentos")


def test_terminal_permission_is_off_by_default():
    from security.manager import PermissionManager

    manager = PermissionManager({})
    assert manager.is_allowed("terminal.run") is False
    assert manager.is_allowed("system.info") is True


def test_permission_changes_persist(tmp_path):
    from security.manager import PermissionManager

    path = tmp_path / "perms.json"
    PermissionManager({}, persist_path=path).set_permission("terminal.run", True)
    assert PermissionManager({}, persist_path=path).is_allowed("terminal.run") is True
