"""Fase 3 — camada de abstração multi-modelo (Claude, GPT, Gemini e modo offline).

Além de conversar, os provedores com suporte a ferramentas (Claude e OpenAI)
recebem as skills registradas como *tools*: um pedido livre como "deixa o som
mais baixo e me lembra da reunião em 15 minutos" vira chamadas reais às skills,
sempre passando por permissões e confirmação.
"""

from __future__ import annotations

import json
import logging
import os
from abc import ABC
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable

try:
    import anthropic
except ImportError:  # pragma: no cover
    anthropic = None

try:
    import openai
except ImportError:  # pragma: no cover
    openai = None

try:
    import google.generativeai as google_generativeai
except ImportError:  # pragma: no cover
    google_generativeai = None

logger = logging.getLogger("jarvis.ai")

DEFAULT_MODELS = {
    "anthropic": "claude-opus-5-5",
    "openai": "gpt-4o-mini",
    "gemini": "gemini-1.5-flash",
}
MAX_TOOL_ROUNDS = 8
ANTHROPIC_FALLBACK_BETA = "server-side-fallback-2026-07-01"

BASE_SYSTEM_PROMPT = (
    "Você é o JARVIS, assistente pessoal que roda no notebook Windows do usuário e conversa em "
    "português do Brasil. Responda de forma curta, natural e direta: suas respostas costumam ser "
    "lidas em voz alta, então evite markdown, listas longas e emojis. Quando o pedido exigir agir "
    "no computador, use as ferramentas disponíveis em vez de explicar como fazer; se precisar de "
    "várias ações, faça todas. Se nenhuma ferramenta atender ao pedido, diga isso com clareza em "
    "vez de inventar. Nunca afirme que executou algo que nenhuma ferramenta confirmou."
)


@dataclass
class ToolSpec:
    """Ferramenta oferecida ao modelo (derivada de uma skill)."""

    name: str
    description: str
    input_schema: dict[str, Any]


ToolCaller = Callable[[str, dict[str, Any]], str]


def build_system_prompt(context: dict[str, Any] | None) -> str:
    context = context or {}
    parts = [context.get("system_prompt") or BASE_SYSTEM_PROMPT]
    if context.get("user_name"):
        parts.append(f"O usuário se chama {context['user_name']}; trate-o pelo nome quando for natural.")
    return "\n\n".join(parts)


def _history(context: dict[str, Any] | None) -> list[dict[str, str]]:
    """Histórico recente como mensagens alternadas user/assistant."""
    messages: list[dict[str, str]] = []
    for item in (context or {}).get("history") or []:
        role = item.get("role")
        content = str(item.get("content") or "").strip()
        if role not in ("user", "assistant") or not content:
            continue
        if messages and messages[-1]["role"] == role:
            messages[-1]["content"] += "\n" + content
        else:
            messages.append({"role": role, "content": content})
    while messages and messages[0]["role"] != "user":
        messages.pop(0)
    if messages and messages[-1]["role"] == "user":
        messages.pop()
    return messages


class AIProvider(ABC):
    """Interface mínima para provedores de IA."""

    supports_tools = False

    def get_response(self, text: str, context: dict[str, Any] | None = None) -> str:
        raise NotImplementedError

    def run_with_tools(
        self,
        text: str,
        tools: list[ToolSpec],
        call_tool: ToolCaller,
        context: dict[str, Any] | None = None,
    ) -> str:
        return self.get_response(text, context)


class AnthropicProvider(AIProvider):
    """Claude via SDK oficial da Anthropic, com laço manual de tool use."""

    supports_tools = True

    def __init__(self, model: str = DEFAULT_MODELS["anthropic"], client: Any = None) -> None:
        if client is None:
            if anthropic is None:
                raise ImportError("Instale `anthropic` para usar o Claude: pip install anthropic")
            client = anthropic.Anthropic()
        self.client = client
        self.model = model

    def _create(self, **kwargs: Any) -> Any:
        return self.client.beta.messages.create(
            model=self.model,
            max_tokens=16000,
            output_config={"effort": "low"},  # respostas rápidas para voz
            betas=[ANTHROPIC_FALLBACK_BETA],
            # se o modelo recusar por política, a API refaz o pedido com um modelo alternativo
            fallbacks="default",
            **kwargs,
        )

    @staticmethod
    def _text(response: Any) -> str:
        return "\n".join(block.text for block in response.content if getattr(block, "type", "") == "text").strip()

    @staticmethod
    def _echoable(content: list[Any]) -> list[Any]:
        """Conteúdo a devolver no histórico, descartando o que veio antes de um fallback."""
        last_fallback = max((i for i, block in enumerate(content) if getattr(block, "type", "") == "fallback"), default=-1)
        kept = []
        for index, block in enumerate(content):
            kind = getattr(block, "type", "")
            if kind == "fallback":
                continue
            if index < last_fallback and kind != "text":
                continue
            kept.append(block)
        return kept

    def get_response(self, text: str, context: dict[str, Any] | None = None) -> str:
        return self.run_with_tools(text, [], lambda name, args: "", context)

    def run_with_tools(
        self,
        text: str,
        tools: list[ToolSpec],
        call_tool: ToolCaller,
        context: dict[str, Any] | None = None,
    ) -> str:
        messages: list[dict[str, Any]] = [*_history(context), {"role": "user", "content": text}]
        tool_params = [
            {"name": tool.name, "description": tool.description, "input_schema": tool.input_schema} for tool in tools
        ]
        system = build_system_prompt(context)

        for _ in range(MAX_TOOL_ROUNDS):
            kwargs: dict[str, Any] = {"system": system, "messages": messages}
            if tool_params:
                kwargs["tools"] = tool_params
            response = self._create(**kwargs)

            if response.stop_reason == "refusal":
                return "Desculpe, não posso ajudar com esse pedido."
            if response.stop_reason != "tool_use":
                return self._text(response) or "Pronto."

            messages.append({"role": "assistant", "content": self._echoable(list(response.content))})
            results = []
            for block in response.content:
                if getattr(block, "type", "") != "tool_use":
                    continue
                try:
                    output = call_tool(block.name, dict(block.input or {}))
                    results.append({"type": "tool_result", "tool_use_id": block.id, "content": output})
                except Exception as exc:  # a falha volta para o modelo decidir o que dizer
                    logger.exception("Ferramenta %s falhou", block.name)
                    results.append(
                        {"type": "tool_result", "tool_use_id": block.id, "content": f"Erro: {exc}", "is_error": True}
                    )
            messages.append({"role": "user", "content": results})

        return "Executei várias ações, mas parei para não entrar em loop. Pode verificar se está tudo certo?"


class OpenAIProvider(AIProvider):
    """Modelos GPT via SDK `openai` (>= 1.0), com function calling."""

    supports_tools = True

    def __init__(self, model: str = DEFAULT_MODELS["openai"], client: Any = None) -> None:
        if client is None:
            if openai is None:
                raise ImportError("OpenAI não está instalado. Instale `openai` para usar este provedor.")
            if not os.getenv("OPENAI_API_KEY"):
                raise RuntimeError("OPENAI_API_KEY não encontrado nas variáveis de ambiente.")
            client = openai.OpenAI()
        self.client = client
        self.model = model

    def get_response(self, text: str, context: dict[str, Any] | None = None) -> str:
        return self.run_with_tools(text, [], lambda name, args: "", context)

    def run_with_tools(
        self,
        text: str,
        tools: list[ToolSpec],
        call_tool: ToolCaller,
        context: dict[str, Any] | None = None,
    ) -> str:
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": build_system_prompt(context)},
            *_history(context),
            {"role": "user", "content": text},
        ]
        tool_params = [
            {
                "type": "function",
                "function": {"name": tool.name, "description": tool.description, "parameters": tool.input_schema},
            }
            for tool in tools
        ]
        for _ in range(MAX_TOOL_ROUNDS):
            kwargs: dict[str, Any] = {"model": self.model, "messages": messages}
            if tool_params:
                kwargs["tools"] = tool_params
            completion = self.client.chat.completions.create(**kwargs)
            message = completion.choices[0].message
            tool_calls = getattr(message, "tool_calls", None) or []
            if not tool_calls:
                return (message.content or "").strip() or "Pronto."

            messages.append(
                {
                    "role": "assistant",
                    "content": message.content or "",
                    "tool_calls": [
                        {"id": call.id, "type": "function", "function": {"name": call.function.name, "arguments": call.function.arguments}}
                        for call in tool_calls
                    ],
                }
            )
            for call in tool_calls:
                try:
                    arguments = json.loads(call.function.arguments or "{}")
                    output = call_tool(call.function.name, arguments)
                except Exception as exc:
                    logger.exception("Ferramenta %s falhou", call.function.name)
                    output = f"Erro: {exc}"
                messages.append({"role": "tool", "tool_call_id": call.id, "content": output})

        return "Executei várias ações, mas parei para não entrar em loop."


class GoogleGeminiProvider(AIProvider):
    def __init__(self, model: str = DEFAULT_MODELS["gemini"]) -> None:
        if google_generativeai is None:
            raise ImportError("google-generativeai não está instalado. Instale `google-generativeai` para usar este provedor.")
        self.model = model

    def get_response(self, text: str, context: dict[str, Any] | None = None) -> str:
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise RuntimeError("GOOGLE_API_KEY não encontrado nas variáveis de ambiente.")

        google_generativeai.configure(api_key=api_key)
        model = google_generativeai.GenerativeModel(self.model)
        history = "\n".join(f"{m['role']}: {m['content']}" for m in _history(context))
        prompt = f"{build_system_prompt(context)}\n\n{history}\n\nuser: {text}" if context else text

        response = model.generate_content(prompt)
        return getattr(response, "text", "").strip() or ""


class FallbackAIProvider(AIProvider):
    """Respostas locais quando nenhuma chave de IA está configurada."""

    def get_response(self, text: str, context: dict[str, Any] | None = None) -> str:
        normalized = text.lower()
        if any(phrase in normalized for phrase in ("qual é o seu nome", "qual o seu nome", "quem é você", "quem voce", "como você se chama", "seu nome")):
            return "Eu sou o Jarvis, seu assistente pessoal. Posso responder e executar tarefas no seu computador."
        if any(phrase in normalized for phrase in ("como você está", "tudo bem", "como você")):
            return "Estou bem, pronto para ajudar você com qualquer pergunta ou comando."
        if any(phrase in normalized for phrase in ("que horas são", "horas são", "hora é")):
            return f"Agora são {datetime.now().strftime('%H:%M')}."
        if any(phrase in normalized for phrase in ("que dia é hoje", "data é hoje", "hoje é")):
            return f"Hoje é {datetime.now().strftime('%d/%m/%Y')}."
        if any(phrase in normalized for phrase in ("o que você pode fazer", "o que você faz", "como você ajuda")):
            return "Posso abrir apps e sites, controlar volume, brilho e janelas, tirar prints, criar lembretes e notas. Diga 'ajuda' para ver exemplos."

        suggestion = (context or {}).get("suggestion")
        if suggestion:
            return f"Não entendi bem. Você quis dizer '{suggestion}'?"
        return (
            "Não reconheci esse comando. Diga 'ajuda' para ver o que sei fazer. Para conversar sobre "
            "qualquer assunto, configure ANTHROPIC_API_KEY, OPENAI_API_KEY ou GOOGLE_API_KEY no arquivo .env."
        )


def _detect_provider() -> str:
    if os.getenv("ANTHROPIC_API_KEY"):
        return "anthropic"
    if os.getenv("OPENAI_API_KEY"):
        return "openai"
    if os.getenv("GOOGLE_API_KEY"):
        return "gemini"
    return "offline"


class AIManager:
    def __init__(self, provider_name: str | None = None, model: str | None = None) -> None:
        requested = (provider_name or os.getenv("JARVIS_AI_PROVIDER") or "auto").lower()
        if requested in ("claude",):
            requested = "anthropic"
        if requested in ("google",):
            requested = "gemini"
        self.provider_name = _detect_provider() if requested == "auto" else requested
        self.model = model or os.getenv("JARVIS_AI_MODEL") or DEFAULT_MODELS.get(self.provider_name, "")
        self.provider = self._create_provider()

    def _create_provider(self) -> AIProvider:
        provider = self._build(self.provider_name)
        if isinstance(provider, FallbackAIProvider):
            # provedor fixado sem chave/biblioteca: usa outro que esteja configurado
            detected = _detect_provider()
            if detected not in (self.provider_name, "offline"):
                logger.warning("Provedor '%s' indisponível; usando '%s'", self.provider_name, detected)
                self.provider_name = detected
                self.model = DEFAULT_MODELS[detected]  # o modelo configurado era do outro provedor
                provider = self._build(detected)
        if isinstance(provider, FallbackAIProvider):
            self.provider_name = "offline"
        return provider

    def _build(self, name: str) -> AIProvider:
        self.provider_name = name
        if self.provider_name == "anthropic" and anthropic is not None and os.getenv("ANTHROPIC_API_KEY"):
            try:
                return AnthropicProvider(model=self.model)
            except Exception as exc:
                logger.warning("Falha ao inicializar AnthropicProvider: %s", exc)

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

        if self.provider_name == "anthropic" and anthropic is None:
            logger.warning("Claude solicitado, mas o pacote `anthropic` não está instalado.")
        if self.provider_name == "gemini" and google_generativeai is None:
            logger.warning("gemini solicitado, mas google-generativeai não está instalado.")

        logger.info("Usando respostas offline; provedor solicitado: %s", self.provider_name)
        return FallbackAIProvider()

    @property
    def supports_tools(self) -> bool:
        return self.provider.supports_tools

    @property
    def is_offline(self) -> bool:
        return isinstance(self.provider, FallbackAIProvider)

    def get_response(self, text: str, context: dict[str, Any] | None = None) -> str:
        try:
            return self.provider.get_response(text, context)
        except Exception as exc:
            logger.exception("Falha ao obter resposta do provedor de IA: %s", exc)
            return FallbackAIProvider().get_response(text, context)

    def run_agent(
        self,
        text: str,
        tools: list[ToolSpec],
        call_tool: ToolCaller,
        context: dict[str, Any] | None = None,
    ) -> str:
        if not self.supports_tools:
            return self.get_response(text, context)
        try:
            return self.provider.run_with_tools(text, tools, call_tool, context)
        except Exception as exc:
            logger.exception("Falha no agente de IA: %s", exc)
            return "Tive um problema para falar com a IA agora. Tente de novo em instantes."
