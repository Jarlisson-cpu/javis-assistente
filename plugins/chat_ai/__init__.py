"""Plugin de chat: responde qualquer pedido que não seja um comando direto.

Com Claude ou OpenAI configurados, o pedido vai para um agente que enxerga
todas as skills como ferramentas — "faça qualquer coisa" vira ações reais no
notebook. Sem chave de IA, responde localmente e sugere o comando mais parecido.
"""

from __future__ import annotations

import asyncio
from typing import Any

import security.manager as security_manager
from ai import AIManager, ToolSpec
from core.event_bus import Event, EventBus
from core.logger import get_logger
from core.plugin_loader import Plugin
from skills import SkillExecutor, SkillRegistry, registry as default_registry
from users import context as user_context

logger = get_logger("plugin.chat_ai")

HISTORY_MESSAGES = 12
TOOL_TIMEOUT_SECONDS = 180

LEGACY_COMMAND_PREFIXES = (
    "buscar ",
    "busca ",
    "busque ",
    "pesquisar ",
    "pesquisa ",
    "pesquise ",
    "procurar ",
    "procura ",
    "procure ",
    "ler site ",
    "ler imagem ",
    "rascunho email ",
    "buscar música ",
    "buscar vídeo ",
    "buscar video ",
    "abrir ",
    "abre ",
    "abra ",
    "inicia ",
    "iniciar ",
    "inicie ",
    "criar arquivo ",
    "ler arquivo ",
    "apagar arquivo ",
    "planejar ",
    "revisar ",
    "explicar ",
)


class ChatAIPlugin(Plugin):
    name = "chat_ai"
    version = "1.0.0"
    description = "Conversa e executa pedidos livres com IA (Claude, GPT ou Gemini) usando as skills como ferramentas."

    def __init__(self, registry: SkillRegistry | None = None) -> None:
        self._ai_manager = AIManager()
        self._registry = registry or default_registry
        self._event_bus: EventBus | None = None
        self._core: Any = None

    def setup(self, event_bus: EventBus) -> None:
        self._event_bus = event_bus
        event_bus.subscribe("user_message", self._on_user_message)

    def attach_core(self, core: Any) -> None:
        self._core = core

    # ------------------------------------------------------------------ roteamento
    def _is_command(self, normalized: str) -> bool:
        if normalized in ("planejar", "revisar", "explicar"):
            return True
        if any(normalized.startswith(prefix) for prefix in LEGACY_COMMAND_PREFIXES):
            return True
        if any(keyword in normalized for keyword in ("permissão", "permissões", "política", "senha")):
            return True
        return self._registry.match(normalized) is not None

    async def _on_user_message(self, event: Event) -> None:
        payload = event.payload or {}
        text = (payload.get("text") or "").strip()
        if not text or self._is_command(text.lower()):
            return

        context = self._context(text)
        if self._ai_manager.supports_tools:
            loop = asyncio.get_running_loop()
            executor = self._executor()

            def call_tool(tool_name: str, arguments: dict[str, Any]) -> str:
                skill = self._registry.by_tool_name(tool_name)
                if skill is None:
                    return f"Ferramenta desconhecida: {tool_name}"
                params = {key: str(value) for key, value in (arguments or {}).items() if value not in (None, "")}
                future = asyncio.run_coroutine_threadsafe(executor.execute(skill, params), loop)
                return future.result(timeout=TOOL_TIMEOUT_SECONDS)

            response = await asyncio.to_thread(
                self._ai_manager.run_agent, text, self._tools(), call_tool, context
            )
        else:
            response = await asyncio.to_thread(self._ai_manager.get_response, text, context)

        if self._event_bus is not None and response:
            await self._event_bus.publish(Event(name="system_message", payload={"text": response}, source="jarvis"))

    # ------------------------------------------------------------------ apoio
    def _tools(self) -> list[ToolSpec]:
        return [
            ToolSpec(name=skill.tool_name, description=skill.description, input_schema=skill.tool_schema())
            for skill in self._registry.list()
        ]

    def _executor(self) -> SkillExecutor:
        if self._core is not None:
            return SkillExecutor(self._core.permission_manager, self._core.confirmation)
        return SkillExecutor(security_manager.manager, getattr(self._event_bus, "confirmation_gate", None))

    def _context(self, text: str) -> dict[str, Any]:
        context: dict[str, Any] = {}
        name = user_context.display_name()
        if name:
            context["user_name"] = name
        if self._core is not None:
            try:
                records = list(self._core.memory.list_messages(limit=HISTORY_MESSAGES))
                context["history"] = [
                    {"role": "assistant" if record.source == "jarvis" else "user", "content": record.text}
                    for record in reversed(records)
                ]
            except Exception:
                logger.exception("Falha ao carregar histórico para a IA")
        if self._ai_manager.is_offline:
            suggestion = self._registry.suggest(text)
            if suggestion:
                context["suggestion"] = suggestion[0]
        return context
