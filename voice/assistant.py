"""Laço de conversa por voz: palavra de ativação, modo conversa e confirmação falada.

Fluxo:
  1. Em espera, só reage a frases que contenham a palavra de ativação
     ("Jarvis, abre o Spotify" ou "Jarvis" seguido do comando).
  2. Depois de atender, entra em *modo conversa* por alguns segundos: dá para
     emendar outro pedido sem repetir "Jarvis".
  3. Enquanto o JARVIS fala, o microfone não escuta (evita ouvir a própria voz).
  4. "Dispensado"/"pode dormir" volta à espera; "encerrar assistente" sai.
"""

from __future__ import annotations

import asyncio
import re
import time
from typing import Any, Callable

from core.confirmation import ConfirmationProvider, DestructiveAction
from core.event_bus import Event
from core.logger import get_logger
from core.text import normalize, strip_accents

logger = get_logger("voice.assistant")

EXIT_COMMANDS = ("sair", "encerrar", "encerrar assistente", "desligar assistente", "fechar assistente", "tchau jarvis")
SLEEP_COMMANDS = ("dispensado", "pode dormir", "pode ir", "obrigado e so isso", "so isso", "nada", "nada nao", "deixa")
STOP_SPEAKING = ("para", "parar", "chega", "silencio", "cala a boca", "ja entendi", "pode parar")
YES_WORDS = ("sim", "pode", "confirmo", "confirma", "claro", "isso", "positivo", "manda ver", "faz", "pode sim", "ok")
NO_WORDS = ("nao", "cancela", "cancelar", "negativo", "deixa", "para")


def extract_command(transcript: str, wake_words: str | list[str] | tuple[str, ...]) -> str | None:
    """Retorna o texto depois da palavra de ativação ou None se ela não foi dita.

    Retorna "" quando a pessoa disse só "Jarvis" (o comando vem na próxima frase).
    """
    words = [wake_words] if isinstance(wake_words, str) else list(wake_words)
    words = [w.strip() for w in words if w and w.strip()]
    if not words:
        return transcript.strip()

    plain = strip_accents(transcript)
    alternatives = "|".join(re.escape(strip_accents(word)) for word in sorted(words, key=len, reverse=True))
    match = re.search(rf"\b(?:{alternatives})\b", plain, re.IGNORECASE)
    if not match:
        return None
    before = transcript[: match.start()].strip(" \t,.:;!?-")
    after = transcript[match.end() :].strip(" \t,.:;!?-")
    # "ok jarvis, ..." / "ei jarvis ..." — descarta interjeições antes do nome
    if normalize(before, drop_polite=False) in ("", "ei", "ok", "oi", "e ai", "fala", "hey", "o", "olha"):
        return after
    return f"{before} {after}".strip()


def _is_one_of(text: str, options: tuple[str, ...]) -> bool:
    return normalize(text, drop_polite=False) in options


def _beep(frequency: int = 880, duration_ms: int = 90) -> None:
    try:
        import winsound

        winsound.Beep(frequency, duration_ms)
    except Exception:
        pass


class VoiceConfirmationProvider(ConfirmationProvider):
    """Pergunta em voz alta e espera "sim" ou "não"."""

    def __init__(self, voice: Any, attempts: int = 2) -> None:
        self._voice = voice
        self._attempts = attempts

    async def ask(self, action: DestructiveAction) -> bool:
        self._voice.speak(f"Confirma: {action.description}? Diga sim ou não.", wait=True)
        for _ in range(self._attempts):
            answer = await asyncio.to_thread(self._voice.listen, 7, 5)
            normalized = normalize(answer or "", drop_polite=False)
            print(f"você (confirmação)> {answer or '...'}")
            words = set(normalized.split())
            if normalized in NO_WORDS or words & {"nao", "cancela", "negativo"}:
                return False
            if normalized in YES_WORDS or words & {"sim", "confirmo", "confirma"}:
                return True
            if answer:
                self._voice.speak("Não entendi. Sim ou não?", wait=True)
        self._voice.speak("Sem confirmação, cancelei.", wait=True)
        return False


class VoiceAssistant:
    def __init__(
        self,
        core: Any,
        output: Callable[[str], None] = print,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.core = core
        self.voice = core.voice
        self.config = core.config.voice
        self.output = output
        self.clock = clock
        self.conversation_until = 0.0
        self.running = False

    @property
    def wake_words(self) -> list[str]:
        words = [self.config.wake_word, *getattr(self.config, "wake_word_aliases", [])]
        return list(dict.fromkeys(w for w in words if w))

    def in_conversation(self) -> bool:
        return self.clock() < self.conversation_until

    def _extend_conversation(self) -> None:
        self.conversation_until = self.clock() + float(getattr(self.config, "conversation_timeout_seconds", 25))

    def _wake_feedback(self) -> None:
        if getattr(self.config, "beep", True):
            _beep()

    async def _listen(self, seconds: int) -> str | None:
        # não escuta enquanto o próprio JARVIS fala
        await asyncio.to_thread(self.voice.wait_until_done)
        return await asyncio.to_thread(
            self.voice.listen, seconds, int(getattr(self.config, "phrase_seconds", 15))
        )

    async def next_command(self) -> str | None:
        """Escuta uma frase e devolve o comando a executar (ou None)."""
        listen_seconds = int(getattr(self.config, "listen_seconds", 6))
        transcript = await self._listen(listen_seconds)
        if not transcript:
            return None

        if self.in_conversation():
            command = extract_command(transcript, self.wake_words)
            return transcript.strip() if command is None else command

        command = extract_command(transcript, self.wake_words)
        if command is None:
            logger.debug("Ignorado (sem palavra de ativação): %s", transcript)
            return None
        self._wake_feedback()
        if command:
            return command

        self.output("Ouvindo comando...")
        follow_up = await self._listen(listen_seconds + 2)
        return follow_up.strip() if follow_up else None

    async def handle(self, command: str) -> bool:
        """Processa um comando; retorna False quando o assistente deve encerrar."""
        if _is_one_of(command, EXIT_COMMANDS):
            self.voice.speak("Até logo.", wait=True)
            return False
        if _is_one_of(command, SLEEP_COMMANDS):
            self.conversation_until = 0.0
            self.voice.speak("Tudo bem, é só chamar.")
            return True
        if _is_one_of(command, STOP_SPEAKING):
            self.voice.stop_speaking()
            return True

        self.output(f"você> {command}")
        await self.core.event_bus.publish(Event(name="user_message", payload={"text": command}, source="voice"))
        self._extend_conversation()
        return True

    async def run(self) -> None:
        self.running = True
        self.config.enable_stt = True
        engine = self.voice.resolve_stt_engine()
        self.output(
            f"\nVoz ativa ({engine}). Diga '{self.config.wake_word}' e o pedido — "
            "ex.: 'Jarvis, aumenta o volume'. Diga 'encerrar assistente' para sair.\n"
        )
        while self.running:
            try:
                command = await self.next_command()
                if command and not await self.handle(command):
                    break
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Erro no laço de voz; continuando")
                await asyncio.sleep(1)
        self.running = False
