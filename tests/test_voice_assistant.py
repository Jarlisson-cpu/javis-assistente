from types import SimpleNamespace

import pytest

from config.schema import VoiceConfig
from core.event_bus import EventBus
from voice.assistant import VoiceAssistant, VoiceConfirmationProvider, extract_command
from voice.manager import clean_for_speech


def test_extract_command_accepts_wake_word_variants():
    words = ["jarvis", "jarbas"]
    assert extract_command("Jarbas abre o spotify", words) == "abre o spotify"
    assert extract_command("ok jarvis, que horas são", words) == "que horas são"
    assert extract_command("abre o chrome jarvis", words) == "abre o chrome"
    assert extract_command("abre o chrome", words) is None
    assert extract_command("Jarvis", words) == ""


def test_clean_for_speech_strips_markdown_and_limits_length():
    assert clean_for_speech("**Olá** veja https://x.com/abc") == "Olá veja link"
    long = clean_for_speech("Frase curta. " * 100, max_chars=60)
    assert long.endswith("O restante está na tela.")
    assert len(long) < 100


class FakeVoice:
    def __init__(self, phrases):
        self.phrases = list(phrases)
        self.spoken = []
        self.stopped = False

    def listen(self, timeout=5, phrase_limit=None):
        return self.phrases.pop(0) if self.phrases else None

    def wait_until_done(self, timeout=120):
        pass

    def speak(self, text, wait=False):
        self.spoken.append(text)

    def stop_speaking(self):
        self.stopped = True

    def resolve_stt_engine(self):
        return "fake"


def make_assistant(phrases, now):
    bus = EventBus()
    messages = []
    bus.subscribe("user_message", lambda e: messages.append(e.payload["text"]))
    voice = FakeVoice(phrases)
    core = SimpleNamespace(voice=voice, event_bus=bus, config=SimpleNamespace(voice=VoiceConfig()))
    assistant = VoiceAssistant(core, output=lambda text: None, clock=lambda: now[0])
    return assistant, messages, voice


@pytest.mark.asyncio
async def test_conversation_mode_accepts_follow_ups_without_wake_word():
    now = [0.0]
    assistant, messages, _ = make_assistant(
        ["conversa aleatória na sala", "Jarvis aumenta o volume", "e tira um print", "pode dormir", "abre o chrome"], now
    )

    for _ in range(5):
        command = await assistant.next_command()
        if command:
            await assistant.handle(command)
        now[0] += 1

    assert messages == ["aumenta o volume", "e tira um print"]


@pytest.mark.asyncio
async def test_conversation_mode_expires():
    now = [0.0]
    assistant, messages, _ = make_assistant(["jarvis que horas são", "abre o chrome"], now)
    await assistant.handle(await assistant.next_command())
    now[0] += 60
    assert await assistant.next_command() is None
    assert messages == ["que horas são"]


@pytest.mark.asyncio
async def test_wake_word_alone_waits_for_command_and_exit_stops():
    now = [0.0]
    assistant, messages, voice = make_assistant(["jarvis", "bloqueia a tela", "jarvis encerrar assistente"], now)
    await assistant.handle(await assistant.next_command())
    assert messages == ["bloqueia a tela"]
    assert await assistant.handle(await assistant.next_command()) is False
    assert voice.spoken[-1] == "Até logo."


@pytest.mark.asyncio
async def test_voice_confirmation_understands_yes_and_no():
    from core.confirmation import DestructiveAction

    action = DestructiveAction(key="system.shutdown", description="Desligar o computador")
    assert await VoiceConfirmationProvider(FakeVoice(["sim pode"])).ask(action) is True
    assert await VoiceConfirmationProvider(FakeVoice(["não"])).ask(action) is False
    assert await VoiceConfirmationProvider(FakeVoice(["hã?", None])).ask(action) is False
