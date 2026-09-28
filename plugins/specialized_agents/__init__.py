"""Agentes de planejamento, revisão e explicação sobre o AIManager existente."""

from __future__ import annotations

from ai import AIManager
from core.event_bus import Event, EventBus
from core.logger import get_logger
from core.plugin_loader import Plugin

logger = get_logger("plugin.specialized_agents")


class SpecializedAgentsPlugin(Plugin):
    name = "specialized_agents"
    version = "0.1.0"
    description = "Agentes focados em planejamento, revisão e explicações técnicas."

    _agents = {
        "planejar": (
            "Agente de planejamento. Transforme o objetivo em um plano prático, "
            "ordenado por etapas, com pré-requisitos, riscos e critérios de conclusão. "
            "Não execute ações; peça esclarecimentos se faltarem dados essenciais."
        ),
        "revisar": (
            "Agente revisor. Analise o material fornecido, priorize problemas concretos, "
            "explique impacto e proponha correções específicas. Não invente fatos ausentes."
        ),
        "explicar": (
            "Agente explicador. Explique o assunto em português claro, começando pelo "
            "essencial e adaptando a profundidade ao pedido. Use exemplos curtos quando úteis."
        ),
    }

    def __init__(self) -> None:
        self._ai_manager = AIManager()
        self._event_bus: EventBus | None = None

    def setup(self, event_bus: EventBus) -> None:
        self._event_bus = event_bus
        event_bus.subscribe("user_message", self._on_user_message)

    @classmethod
    def handles(cls, text: str) -> bool:
        normalized = text.strip().lower()
        return any(normalized == name or normalized.startswith(f"{name} ") for name in cls._agents)

    async def _on_user_message(self, event: Event) -> None:
        text = str((event.payload or {}).get("text", "")).strip()
        normalized = text.lower()
        agent_name = next(
            (name for name in self._agents if normalized == name or normalized.startswith(f"{name} ")),
            None,
        )
        if agent_name is None:
            return

        task = text[len(agent_name) :].strip(" :,-")
        if not task:
            response = f"Descreva o que você quer que eu {agent_name}."
        else:
            response = self._ai_manager.get_response(
                task,
                context={"system_prompt": self._agents[agent_name]},
            )

        logger.info("Agente especializado acionado: %s", agent_name)
        if self._event_bus:
            await self._event_bus.publish(
                Event(name="system_message", payload={"text": response}, source="jarvis")
            )