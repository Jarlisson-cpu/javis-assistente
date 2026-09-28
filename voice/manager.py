from __future__ import annotations

import logging
import json
import queue
import threading
import time
from typing import Any, Optional

logger = logging.getLogger("voice")


class VoiceManager:
    def __init__(self, config: Any = None) -> None:
        self.config = config or {}
        self._tts = None
        self._tts_lock = threading.Lock()
        self._vosk_model = None
        if getattr(self.config, "enable_tts", True):
            try:
                import pyttsx3

                self._tts = pyttsx3.init()
            except Exception:
                logger.info("pyttsx3 não disponível; TTS ficará inativo")
        else:
            logger.info("TTS desabilitado via configuração")

    def speak(self, text: str) -> None:
        if self._tts:
            try:
                with self._tts_lock:
                    self._tts.say(text)
                    self._tts.runAndWait()
            except Exception:
                logger.exception("Falha ao reproduzir TTS")
        else:
            logger.info("TTS (simulado): %s", text)

    def listen(self, timeout: int = 5) -> str | None:
        if not getattr(self.config, "enable_stt", False):
            return None

        engine = getattr(self.config, "stt_engine", "vosk").lower()
        if engine != "vosk":
            logger.warning("Mecanismo STT não suportado: %s", engine)
            return None

        try:
            import sounddevice
            import vosk

            if self._vosk_model is None:
                model_path = getattr(self.config, "stt_model_path", "models/vosk")
                self._vosk_model = vosk.Model(model_path)

            sample_rate = getattr(self.config, "stt_sample_rate", 16000)
            recognizer = vosk.KaldiRecognizer(self._vosk_model, sample_rate)
            audio_chunks: queue.Queue[bytes] = queue.Queue()

            def capture_audio(indata, frames, timing, status) -> None:
                if status:
                    logger.warning("Aviso na captura de áudio: %s", status)
                audio_chunks.put(bytes(indata))

            with sounddevice.RawInputStream(
                samplerate=sample_rate,
                blocksize=4000,
                dtype="int16",
                channels=1,
                callback=capture_audio,
            ):
                deadline = time.monotonic() + max(float(timeout), 0.0)
                while time.monotonic() < deadline:
                    try:
                        chunk = audio_chunks.get(timeout=max(deadline - time.monotonic(), 0.01))
                    except queue.Empty:
                        break
                    if recognizer.AcceptWaveform(chunk):
                        transcript = json.loads(recognizer.Result()).get("text", "").strip()
                        if transcript:
                            return transcript

            transcript = json.loads(recognizer.FinalResult()).get("text", "").strip()
            return transcript or None
        except Exception:
            logger.exception("Falha no reconhecimento de voz via Vosk")
            return None
