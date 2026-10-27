"""Plugin de exemplo — modelo para criar novos comandos do JARVIS.

Um plugin pode (a) assinar eventos no `event_bus` ou (b), o mais comum,
registrar skills. Uma skill registrada funciona automaticamente por texto, por
voz, na interface web e também como ferramenta para o agente de IA.
"""

from __future__ import annotations

import random

from core.event_bus import EventBus
from core.logger import get_logger
from core.plugin_loader import Plugin
from skills import Skill, registry
from users import context as user_context

logger = get_logger("plugins.example_greeting")

_THANKS_REPLIES = ("Por nada{name}!", "Disponha{name}.", "Sempre às ordens{name}.")


def _thanks(params: dict[str, str]) -> str:
    name = user_context.display_name()
    return random.choice(_THANKS_REPLIES).format(name=f", {name}" if name else "")


class ExampleGreetingPlugin(Plugin):
    name = "example_greeting"
    version = "1.0.0"
    description = "Exemplo de plugin: responde a agradecimentos e mostra como registrar uma skill."

    def setup(self, event_bus: EventBus) -> None:
        registry.register(
            Skill(
                name="conversa.agradecimento",
                description="Responde quando o usuário agradece.",
                # padrões casam com o texto normalizado: minúsculo, sem acentos e sem pontuação
                patterns=[r"(?:muito\s+)?(?:obrigado|obrigada|valeu|vlw|brigado|agradeco)(?:\s+jarvis)?(?:\s+.*)?"],
                handler=_thanks,
                examples=["obrigado"],
                category="conversa",
            )
        )

    def teardown(self) -> None:
        registry.unregister("conversa.agradecimento")
