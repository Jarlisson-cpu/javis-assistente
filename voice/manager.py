"""Voz do JARVIS: reconhecimento (STT) e fala (TTS).

STT
  - ``vosk``: offline e privado; exige um modelo em ``voice.stt_model_path``
    (``python scripts/baixar_modelo_vosk.py`` baixa o modelo em português).
  - ``google``: mais preciso, mas envia o áudio da frase ao Google.
  - ``auto``: Vosk quando há modelo instalado; senão Google.

TTS
  - ``pyttsx3`` (SAPI5) numa thread dedicada — o motor não é thread-safe;
  - ``windows``: voz nativa via PowerShell/System.Speech, sem dependências;
  - ``auto``: pyttsx3 quando instalado, senão a voz nativa.
"""

from __future__ import annotations

import importlib.util
import json
import logging
import math
import os
import queue
import re
import subprocess
import threading
import time
from array import array
from pathlib import Path
from typing import Any

logger = logging.getLogger("jarvis.voice")

CREATE_NO_WINDOW = 0x08000000
_SENTINEL = object()


def _module_available(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


def clean_for_speech(text: str, max_chars: int = 600) -> str:
    """Remove marcação que soaria estranha em voz alta e limita o tamanho."""
    value = re.sub(r"```.*?```", " (código na tela) ", text, flags=re.DOTALL)
    value = re.sub(r"https?://\S+", "link", value)
    value = re.sub(r"[*_#`>|~]+", "", value)
    value = re.sub(r"^\s*[-•]\s+", "", value, flags=re.MULTILINE)
    value = re.sub(r"[^\w\s.,;:!?%°ºª()\-/'\"áéíóúâêôãõçàÁÉÍÓÚÂÊÔÃÕÇÀ]", " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    if len(value) > max_chars:
        cut = value[:max_chars]
        cut = cut[: cut.rfind(".") + 1] or cut
        value = cut + " O restante está na tela."
    return value


def _rms(chunk: bytes) -> float:
    samples = array("h")
    samples.frombytes(chunk[: len(chunk) - len(chunk) % 2])
    if not samples:
        return 0.0
    return math.sqrt(sum(sample * sample for sample in samples) / len(samples))


class VoiceManager:
    def __init__(self, config: Any = None) -> None:
        self.config = config or {}
        self._tts = None
        self._tts_lock = threading.Lock()
        self._vosk_model = None
        self._speech_queue: "queue.Queue[object]" = queue.Queue()
        self._speaking = threading.Event()
        self._tts_engine = self._resolve_tts_engine() if getattr(self.config, "enable_tts", True) else None
        if self._tts_engine is None:
            logger.info("TTS desabilitado ou indisponível; respostas ficam só no texto")
        else:
            threading.Thread(target=self._speech_worker, name="jarvis-tts", daemon=True).start()

    # ================================================================== TTS
    def _cfg(self, name: str, default: Any) -> Any:
        return getattr(self.config, name, default)

    def _resolve_tts_engine(self) -> str | None:
        engine = str(self._cfg("tts_engine", "auto")).lower()
        if engine in ("auto", "pyttsx3") and _module_available("pyttsx3"):
            return "pyttsx3"
        if engine in ("auto", "windows") and os.name == "nt":
            return "windows"
        return None

    @property
    def tts_engine(self) -> str | None:
        return self._tts_engine

    def _init_pyttsx3(self) -> Any:
        import pyttsx3

        engine = pyttsx3.init()
        engine.setProperty("rate", int(self._cfg("tts_rate", 190)))
        wanted = str(self._cfg("tts_voice", "")).lower()
        voices = engine.getProperty("voices") or []

        def is_portuguese(voice: Any) -> bool:
            blob = " ".join(
                [str(getattr(voice, "id", "")), str(getattr(voice, "name", "")), *map(str, getattr(voice, "languages", []) or [])]
            ).lower()
            return any(tag in blob for tag in ("pt-br", "pt_br", "portuguese", "brazil", "maria", "daniel", "francisca", "antonio", "1046"))

        chosen = next((v for v in voices if wanted and wanted in str(getattr(v, "name", "")).lower()), None)
        chosen = chosen or next((v for v in voices if is_portuguese(v)), None)
        if chosen is not None:
            engine.setProperty("voice", chosen.id)
        else:
            logger.info("Nenhuma voz em português encontrada; instale uma em Configurações > Hora e idioma > Fala")
        return engine

    def _speak_windows(self, text: str) -> None:
        rate = max(-10, min(10, round((int(self._cfg("tts_rate", 190)) - 180) / 15)))
        script = (
            "Add-Type -AssemblyName System.Speech;"
            "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer;"
            "try { $s.SelectVoiceByHints('NotSet','NotSet',0,[Globalization.CultureInfo]'pt-BR') } catch {};"
            f"$s.Rate = {rate};"
            "$s.Speak([Console]::In.ReadToEnd())"
        )
        subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            input=text,
            text=True,
            encoding="utf-8",
            timeout=120,
            creationflags=CREATE_NO_WINDOW,
            capture_output=True,
        )

    def _speech_worker(self) -> None:
        engine = None
        if self._tts_engine == "pyttsx3":
            try:
                engine = self._init_pyttsx3()
                self._tts = engine
            except Exception:
                logger.exception("pyttsx3 falhou ao iniciar; usando a voz nativa do Windows")
                self._tts_engine = "windows" if os.name == "nt" else None
        while True:
            item = self._speech_queue.get()
            if item is _SENTINEL:
                return
            text = str(item)
            self._speaking.set()
            try:
                if engine is not None:
                    engine.say(text)
                    engine.runAndWait()
                elif self._tts_engine == "windows":
                    self._speak_windows(text)
            except Exception:
                logger.exception("Falha ao reproduzir TTS")
            finally:
                if self._speech_queue.empty():
                    self._speaking.clear()

    def speak(self, text: str, wait: bool = False) -> None:
        cleaned = clean_for_speech(text, int(self._cfg("speak_max_chars", 600)))
        if not cleaned:
            return
        if self._tts_engine is None:
            logger.info("TTS (simulado): %s", cleaned)
            return
        self._speaking.set()
        self._speech_queue.put(cleaned)
        if wait:
            self.wait_until_done()

    def is_speaking(self) -> bool:
        return self._speaking.is_set()

    def wait_until_done(self, timeout: float = 120.0) -> None:
        deadline = time.monotonic() + timeout
        while self._speaking.is_set() and time.monotonic() < deadline:
            time.sleep(0.05)

    def stop_speaking(self) -> None:
        """Descarta falas pendentes (a frase atual termina)."""
        try:
            while True:
                self._speech_queue.get_nowait()
        except queue.Empty:
            pass
        if self._tts is not None:
            try:
                self._tts.stop()
            except Exception:
                pass

    # ================================================================== STT
    def resolve_stt_engine(self) -> str | None:
        engine = str(self._cfg("stt_engine", "vosk")).lower()
        if engine == "vosk":
            return "vosk"
        if engine == "google":
            return "google"
        has_audio = _module_available("sounddevice")
        if has_audio and _module_available("vosk") and Path(self._cfg("stt_model_path", "models/vosk")).is_dir():
            return "vosk"
        if has_audio and _module_available("speech_recognition"):
            return "google"
        return None

    def stt_unavailable_reason(self) -> str | None:
        engine = self.resolve_stt_engine()
        missing = [module for module in ("sounddevice",) if not _module_available(module)]
        if engine == "vosk":
            missing += [m for m in ("vosk",) if not _module_available(m)]
            model = Path(self._cfg("stt_model_path", "models/vosk"))
            if missing or not model.is_dir():
                return (
                    f"Vosk indisponível. Instale: {', '.join(missing) or 'ok'}; modelo em {model} "
                    f"({'ok' if model.is_dir() else 'rode: python scripts/baixar_modelo_vosk.py'})."
                )
            return None
        if engine == "google":
            missing += [m for m in ("speech_recognition",) if not _module_available(m)]
            return f"Reconhecimento Google indisponível. Instale: {', '.join(missing)}" if missing else None
        return (
            "Nenhum reconhecimento de voz disponível. Rode 'pip install sounddevice SpeechRecognition' "
            "ou 'pip install sounddevice vosk' + 'python scripts/baixar_modelo_vosk.py'."
        )

    def listen(self, timeout: int = 5, phrase_limit: int | None = None) -> str | None:
        if not getattr(self.config, "enable_stt", False):
            return None

        engine = self.resolve_stt_engine()
        if engine == "vosk":
            return self._listen_vosk(timeout, phrase_limit)
        if engine == "google":
            return self._listen_google(timeout, phrase_limit)
        logger.warning("Mecanismo STT não suportado ou indisponível: %s", self._cfg("stt_engine", "auto"))
        return None

    def _listen_vosk(self, timeout: int, phrase_limit: int | None) -> str | None:
        try:
            import sounddevice
            import vosk

            if self._vosk_model is None:
                model_path = getattr(self.config, "stt_model_path", "models/vosk")
                if hasattr(vosk, "SetLogLevel"):
                    vosk.SetLogLevel(-1)
                self._vosk_model = vosk.Model(model_path)

            sample_rate = getattr(self.config, "stt_sample_rate", 16000)
            recognizer = vosk.KaldiRecognizer(self._vosk_model, sample_rate)
            audio_chunks: queue.Queue[bytes] = queue.Queue()

            def capture_audio(indata, frames, timing, status) -> None:
                if status:
                    logger.debug("Aviso na captura de áudio: %s", status)
                audio_chunks.put(bytes(indata))

            with sounddevice.RawInputStream(
                samplerate=sample_rate,
                blocksize=4000,
                dtype="int16",
                channels=1,
                callback=capture_audio,
            ):
                started = time.monotonic()
                deadline = started + max(float(timeout), 0.0)
                hard_limit = started + float(phrase_limit or timeout + 15)
                heard_speech = False
                while time.monotonic() < (hard_limit if heard_speech else deadline):
                    try:
                        chunk = audio_chunks.get(timeout=0.5)
                    except queue.Empty:
                        continue
                    if recognizer.AcceptWaveform(chunk):
                        transcript = json.loads(recognizer.Result()).get("text", "").strip()
                        if transcript:
                            return transcript
                    elif not heard_speech and hasattr(recognizer, "PartialResult"):
                        heard_speech = bool(json.loads(recognizer.PartialResult()).get("partial", "").strip())

            transcript = json.loads(recognizer.FinalResult()).get("text", "").strip()
            return transcript or None
        except Exception:
            logger.exception("Falha no reconhecimento de voz via Vosk")
            return None

    def record_phrase(self, timeout: float, phrase_limit: float | None = None) -> bytes | None:
        """Grava do microfone até a pessoa parar de falar (detecção de silêncio por energia)."""
        import sounddevice

        sample_rate = int(self._cfg("stt_sample_rate", 16000))
        block = int(sample_rate * 0.1)  # blocos de 100 ms
        silence_blocks = max(3, int(float(self._cfg("silence_seconds", 0.9)) * 10))
        max_blocks = int(float(phrase_limit or self._cfg("phrase_seconds", 15)) * 10)
        chunks: queue.Queue[bytes] = queue.Queue()

        def capture(indata, frames, timing, status) -> None:
            chunks.put(bytes(indata))

        with sounddevice.RawInputStream(
            samplerate=sample_rate, blocksize=block, dtype="int16", channels=1, callback=capture
        ):
            ambient = [_rms(chunks.get(timeout=2)) for _ in range(3)]
            threshold = max(sum(ambient) / len(ambient) * 2.2, 350.0)
            pre_roll: list[bytes] = []
            recorded: list[bytes] = []
            quiet = 0
            deadline = time.monotonic() + float(timeout)
            while True:
                try:
                    chunk = chunks.get(timeout=1)
                except queue.Empty:
                    return None
                loud = _rms(chunk) > threshold
                if not recorded:
                    pre_roll = (pre_roll + [chunk])[-3:]
                    if loud:
                        recorded = list(pre_roll)
                    elif time.monotonic() > deadline:
                        return None
                    continue
                recorded.append(chunk)
                quiet = 0 if loud else quiet + 1
                if quiet >= silence_blocks or len(recorded) >= max_blocks:
                    break
        return b"".join(recorded)

    def _listen_google(self, timeout: int, phrase_limit: int | None) -> str | None:
        try:
            import speech_recognition as sr

            audio = self.record_phrase(timeout, phrase_limit)
            if not audio:
                return None
            sample_rate = int(self._cfg("stt_sample_rate", 16000))
            recognizer = sr.Recognizer()
            try:
                return recognizer.recognize_google(
                    sr.AudioData(audio, sample_rate, 2), language=str(self._cfg("language", "pt-BR"))
                ).strip() or None
            except sr.UnknownValueError:
                return None
            except sr.RequestError as exc:
                logger.warning("Reconhecimento Google indisponível (sem internet?): %s", exc)
                return None
        except Exception:
            logger.exception("Falha no reconhecimento de voz via Google")
            return None
