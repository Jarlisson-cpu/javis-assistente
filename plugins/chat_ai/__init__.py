"""Plugin de chat genérico para responder perguntas em estilo assistente."""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Optional

from core.event_bus import Event, EventBus
from core.logger import get_logger
from core.plugin_loader import Plugin

logger = get_logger("plugin.chat_ai")

try:
    import openai
except ImportError:  # pragma: no cover
    openai = None


class ChatAIPlugin(Plugin):
    name = "chat_ai"
    version = "0.1.0"
    description = "Responde perguntas de conversa como um assistente de IA."

    def setup(self, event_bus: EventBus) -> None:
        self._event_bus = event_bus
        event_bus.subscribe("user_message", self._on_user_message)

    def _on_user_message(self, event: Event) -> None:
        payload = event.payload or {}
        text = (payload.get("text") or "").strip()
        if not text:
            return

        normalized = text.lower()
        if self._is_command(normalized):
            return

        response = self._get_response(text)
        self._event_bus.publish_sync(Event(name="system_message", payload={"text": response}, source="jarvis"))

    def _is_command(self, normalized: str) -> bool:
        command_prefixes = (
            "buscar ",
            "abrir ",
            "abre ",
            "abra ",
            "criar arquivo ",
            "ler arquivo ",
            "apagar arquivo ",
        )
        if any(normalized.startswith(prefix) for prefix in command_prefixes):
            return True

        if any(keyword in normalized for keyword in ("permissão", "permissões", "política", "senha")):
            return True

        return False

    def _get_response(self, text: str) -> str:
        api_key = os.getenv("OPENAI_API_KEY")
        if openai and api_key:
            try:
                openai.api_key = api_key
                completion = openai.ChatCompletion.create(
                    model="gpt-3.5-turbo",
                    messages=[
                        {"role": "system", "content": "Você é Jarvis, um assistente pessoal que responde de forma clara e útil."},
                        {"role": "user", "content": text},
                    ],
                    max_tokens=250,
                )
                answer = completion.choices[0].message.content.strip()
                if answer:
                    return answer
            except Exception as exc:
                logger.exception("Falha ao chamar OpenAI: %s", exc)

        return self._fallback_response(text)

    def _fallback_response(self, text: str) -> str:
        normalized = text.lower()
        if any(phrase in normalized for phrase in ("qual é o seu nome", "quem é você", "quem voce", "como você se chama")):
            return "Eu sou o Jarvis, seu assistente pessoal. Posso responder e executar tarefas no seu computador."
        if any(phrase in normalized for phrase in ("como você está", "tudo bem", "como você")):
            return "Estou bem, pronto para ajudar você com qualquer pergunta ou comando."
        if any(phrase in normalized for phrase in ("que horas são", "horas são", "hora é")):
            return f"Agora são {datetime.now().strftime('%H:%M')} ."
        if any(phrase in normalized for phrase in ("que dia é hoje", "data é hoje", "hoje é")):
            return f"Hoje é {datetime.now().strftime('%d/%m/%Y')} ."
        if any(phrase in normalized for phrase in ("o que você pode fazer", "o que você faz", "como você ajuda")):
            return "Posso abrir apps, arquivos e sites, responder perguntas simples e executar comandos no seu PC. Pergunte algo ou diga 'abrir site google.com'."

        return (
            "Ainda não tenho um modelo de IA externo configurado, mas posso responder perguntas básicas. "
            "Se você deseja respostas mais avançadas, configure OPENAI_API_KEY no ambiente. "
            "Pergunte outra coisa ou peça para abrir um site."
        )
