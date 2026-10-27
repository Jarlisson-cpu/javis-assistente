"""Skills — comandos de alto nível que o JARVIS sabe executar.

Cada skill declara frases (regex sobre o texto normalizado por
`core.text.normalize`), a permissão que exige e, se for destrutiva, a chave de
confirmação. A mesma lista serve a três consumidores:

- `SkillRouter`: executa comandos digitados ou falados que casam com um padrão;
- o agente de IA: expõe cada skill como ferramenta (tool use), então pedidos em
  linguagem livre ("deixa o som mais baixo e tira um print") também viram ação;
- ajuda/sugestões: `examples` alimenta "o que você sabe fazer" e o "você quis dizer".
"""

from __future__ import annotations

import asyncio
import difflib
import inspect
import re
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from core.confirmation import DestructiveAction
from core.exceptions import ConfirmationDenied
from core.logger import get_logger
from core.text import normalize

logger = get_logger("skills")

SkillHandler = Callable[[dict[str, str]], str | Awaitable[str]]
ConfirmText = str | Callable[[dict[str, str]], str]


def recover_raw(raw_text: str, normalized_value: str) -> str:
    """Recupera o trecho original (com maiúsculas, acentos e pontuação) de um parâmetro.

    Os padrões casam contra o texto normalizado; para parâmetros como o texto a
    digitar, queremos o que o usuário realmente escreveu/disse.
    """
    starts = [match.start() for match in re.finditer(r"\S+", raw_text)]
    ends = [match.end() for match in re.finditer(r"\S+", raw_text)]
    for start in starts:
        for end in reversed(ends):
            if end <= start:
                break
            candidate = raw_text[start:end]
            if normalize(candidate, drop_polite=False) == normalized_value:
                return candidate.strip(" ,")
    return normalized_value


@dataclass
class Skill:
    """Um comando executável pelo JARVIS."""

    name: str
    description: str
    handler: SkillHandler
    patterns: list[str] = field(default_factory=list)
    parameters: dict[str, str] = field(default_factory=dict)
    required: list[str] = field(default_factory=list)
    permission: str | None = None
    confirm_key: str | None = None
    confirm_text: ConfirmText | None = None
    examples: list[str] = field(default_factory=list)
    category: str = "geral"
    matcher: Callable[[str], dict[str, str] | None] | None = None
    raw_params: list[str] = field(default_factory=list)
    _compiled: list[re.Pattern[str]] = field(default_factory=list, init=False, repr=False)

    def __post_init__(self) -> None:
        self._compiled = [re.compile(rf"^(?:{pattern})$") for pattern in self.patterns]

    def match(self, normalized_text: str, raw_text: str | None = None) -> dict[str, str] | None:
        params: dict[str, str] | None = None
        if self.matcher is not None:
            params = self.matcher(normalized_text)
        else:
            for pattern in self._compiled:
                found = pattern.match(normalized_text)
                if found:
                    params = {key: value.strip() for key, value in found.groupdict().items() if value}
                    break
        if params is not None and raw_text:
            for name in self.raw_params:
                if params.get(name):
                    params[name] = recover_raw(raw_text, params[name])
        return params

    @property
    def tool_name(self) -> str:
        return self.name.replace(".", "_")

    def tool_schema(self) -> dict[str, Any]:
        """JSON Schema dos parâmetros, no formato aceito pelos provedores de IA."""
        return {
            "type": "object",
            "properties": {
                key: {"type": "string", "description": description}
                for key, description in self.parameters.items()
            },
            "required": list(self.required),
            "additionalProperties": False,
        }

    def describe_confirmation(self, params: dict[str, str]) -> str:
        if callable(self.confirm_text):
            return self.confirm_text(params)
        return self.confirm_text or self.description


class SkillRegistry:
    """Coleção ordenada de skills: a primeira que casar vence."""

    def __init__(self) -> None:
        self._skills: dict[str, Skill] = {}

    def register(self, skill: Skill) -> Skill:
        if skill.name in self._skills:
            logger.debug("Skill '%s' re-registrada; substituindo a anterior", skill.name)
        self._skills[skill.name] = skill
        return skill

    def unregister(self, name: str) -> None:
        self._skills.pop(name, None)

    def get(self, name: str) -> Skill | None:
        return self._skills.get(name)

    def by_tool_name(self, tool_name: str) -> Skill | None:
        return next((s for s in self._skills.values() if s.tool_name == tool_name), None)

    def list(self) -> list[Skill]:
        return list(self._skills.values())

    def match(self, text: str) -> tuple[Skill, dict[str, str]] | None:
        normalized = normalize(text)
        if not normalized:
            return None
        for skill in self._skills.values():
            params = skill.match(normalized, text)
            if params is not None:
                return skill, params
        return None

    def suggest(self, text: str, limit: int = 1) -> list[str]:
        """Exemplos parecidos com `text` — usado no "você quis dizer...?"."""
        normalized = normalize(text)
        examples = {normalize(example): example for skill in self._skills.values() for example in skill.examples}
        close = difflib.get_close_matches(normalized, list(examples), n=limit, cutoff=0.6)
        return [examples[item] for item in close]

    def help_text(self) -> str:
        by_category: dict[str, list[str]] = {}
        for skill in self._skills.values():
            if skill.examples:
                by_category.setdefault(skill.category, []).append(skill.examples[0])
        lines = [f"{category}: {', '.join(examples)}" for category, examples in by_category.items()]
        return "Posso, por exemplo — " + "; ".join(lines) + "."


class SkillExecutor:
    """Executa uma skill aplicando permissão e confirmação."""

    def __init__(self, permission_manager: Any = None, confirmation: Any = None) -> None:
        self.permission_manager = permission_manager
        self.confirmation = confirmation

    async def execute(self, skill: Skill, params: dict[str, str]) -> str:
        missing = [name for name in skill.required if not params.get(name)]
        if missing:
            return f"Faltou informar: {', '.join(missing)}."

        if skill.permission and self.permission_manager is not None:
            if not self.permission_manager.is_allowed(skill.permission):
                return f"Essa ação está bloqueada pela permissão {skill.permission}."

        if skill.confirm_key:
            if self.confirmation is None:
                return "Ação cancelada: não há como pedir sua confirmação agora."
            try:
                await self.confirmation.confirm(
                    DestructiveAction(key=skill.confirm_key, description=skill.describe_confirmation(params))
                )
            except ConfirmationDenied:
                return "Tudo bem, cancelei."

        try:
            if inspect.iscoroutinefunction(skill.handler):
                result = await skill.handler(params)
            else:
                result = await asyncio.to_thread(skill.handler, params)
                if inspect.isawaitable(result):
                    result = await result
        except (ValueError, PermissionError, RuntimeError, FileNotFoundError) as exc:
            logger.info("Skill %s falhou: %s", skill.name, exc)
            return str(exc)
        except Exception:
            logger.exception("Erro inesperado ao executar a skill %s", skill.name)
            return "Algo deu errado ao executar esse comando. Veja o log para detalhes."
        logger.info("Skill executada: %s %s", skill.name, params)
        return str(result or "Feito.")


registry = SkillRegistry()
