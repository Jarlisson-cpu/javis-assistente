"""Fase 3 — camada de abstração multi-modelo (Claude, GPT, Gemini, Ollama...)."""

from __future__ import annotations

import logging
import os
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

try:
    import openai
except ImportError:  # pragma: no cover
    openai = None

try:
    import google.generativeai as google_generativeai
except ImportError:  # pragma: no cover
    google_generativeai = None

logger = logging.getLogger("ai")


class AIProvider(ABC):
    """Interface mínima para provedores de IA."""

    @abstractmethod
    def get_response(self, text: str, context: dict[str, Any] | None = None) -> str:
        raise NotImplementedError


class OpenAIProvider(AIProvider):
    def __init__(self, model: str = "gpt-3.5-turbo") -> None:
        if openai is None:
            raise ImportError("OpenAI não está instalado. Instale `openai` para usar este provedor.")
        self.model = model

    def get_response(self, text: str, context: dict[str, Any] | None = None) -> str:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY não encontrado nas variáveis de ambiente.")

        openai.api_key = api_key
        messages = [
            {"role": "system", "content": "Você é Jarvis, um assistente pessoal que responde de forma clara e útil."},
            {"role": "user", "content": text},
        ]

        if context:
            messages.insert(1, {"role": "system", "content": context.get("system_prompt", "")})

        completion = openai.ChatCompletion.create(
            model=self.model,
            messages=messages,
            max_tokens=250,
        )
        answer = completion.choices[0].message.content.strip()
        return answer or ""


class GoogleGeminiProvider(AIProvider):
    def __init__(self, model: str = "gemini-1.5-flash") -> None:
        if google_generativeai is None:
            raise ImportError("google-generativeai não está instalado. Instale `google-generativeai` para usar este provedor.")
        self.model = model

    def get_response(self, text: str, context: dict[str, Any] | None = None) -> str:
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise RuntimeError("GOOGLE_API_KEY não encontrado nas variáveis de ambiente.")

        google_generativeai.configure(api_key=api_key)
        model = google_generativeai.GenerativeModel(self.model)
        prompt = text

        if context and context.get("system_prompt"):
            prompt = f"{context['system_prompt']}\n\n{text}"

        response = model.generate_content(prompt)
        return getattr(response, "text", "").strip() or ""


class FallbackAIProvider(AIProvider):
    def get_response(self, text: str, context: dict[str, Any] | None = None) -> str:
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
            "Se você deseja respostas mais avançadas, configure OPENAI_API_KEY ou GOOGLE_API_KEY no ambiente. "
            "Pergunte outra coisa ou peça para abrir um site."
        )


class AIManager:
    def __init__(self, provider_name: str | None = None, model: str | None = None) -> None:
        self.provider_name = provider_name or os.getenv("JARVIS_AI_PROVIDER", "openai")
        self.model = model or os.getenv("JARVIS_AI_MODEL", "gpt-3.5-turbo")
        self.provider = self._create_provider()

    def _create_provider(self) -> AIProvider:
        if self.provider_name == "openai" and openai is not None and os.getenv("OPENAI_API_KEY"):
            try:
                return OpenAIProvider(model=self.model)
            except Exception as exc:
                logger.warning("Falha ao inicializar OpenAIProvider: %s", exc)

        if self.provider_name == "gemini" and google_generativeai is not None and os.getenv("GOOGLE_API_KEY"):
            try:
                return GoogleGeminiProvider(model=self.model)
            except Exception as exc:
                logger.warning("Falha ao inicializar GoogleGeminiProvider: %s", exc)

        if self.provider_name == "gemini" and google_generativeai is None:
            logger.warning("gemini solicitado, mas google-generativeai não está instalado.")

        logger.info("Usando fallback de IA, provedor solicitado: %s", self.provider_name)
        return FallbackAIProvider()

    def get_response(self, text: str, context: dict[str, Any] | None = None) -> str:
        try:
            return self.provider.get_response(text, context)
        except Exception as exc:
            logger.exception("Falha ao obter resposta do provedor de IA: %s", exc)
            return FallbackAIProvider().get_response(text, context)
