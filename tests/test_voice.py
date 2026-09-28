import json
import sys
import types
from types import SimpleNamespace

from main import _extract_voice_command
from voice.manager import VoiceManager


def test_listen_returns_vosk_transcript(monkeypatch):
    class FakeStream:
        def __init__(self, callback, **kwargs):
            self.callback = callback

        def __enter__(self):
            self.callback(b"audio", 1, None, None)
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            return False

    class FakeRecognizer:
        def __init__(self, model, sample_rate):
            pass

        def AcceptWaveform(self, audio):
            return True

        def Result(self):
            return json.dumps({"text": "olá jarvis"})

    monkeypatch.setitem(sys.modules, "sounddevice", types.SimpleNamespace(RawInputStream=FakeStream))
    monkeypatch.setitem(
        sys.modules,
        "vosk",
        types.SimpleNamespace(Model=lambda path: object(), KaldiRecognizer=FakeRecognizer),
    )
    manager = VoiceManager(
        SimpleNamespace(
            enable_tts=False,
            enable_stt=True,
            stt_engine="vosk",
            stt_model_path="models/vosk",
        )
    )

    assert manager.listen(timeout=1) == "olá jarvis"


def test_listen_is_disabled_by_configuration():
    manager = VoiceManager(SimpleNamespace(enable_tts=False, enable_stt=False))

    assert manager.listen(timeout=1) is None


def test_voice_command_requires_and_removes_wake_word():
    assert _extract_voice_command("Jarvis, abra o Chrome", "jarvis") == "abra o Chrome"
    assert _extract_voice_command("abra o Chrome", "jarvis") is None
    assert _extract_voice_command("Jarvis", "jarvis") == ""