from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger("voice")


class VoiceManager:
    def __init__(self, config: Optional[dict] = None) -> None:
        self.config = config or {}
        self._tts = None
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
                self._tts.say(text)
                self._tts.runAndWait()
            except Exception:
                logger.exception("Falha ao reproduzir TTS")
        else:
            logger.info("TTS (simulado): %s", text)

    def listen(self, timeout: int = 5) -> str | None:
        # stub: real STT integration (vosk, whisper) to be added later
        logger.info("listen() chamado — stub retorna None")
        return None
