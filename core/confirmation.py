"""Portão de confirmação para ações destrutivas.

Qualquer ação que apague arquivos, formate discos, desligue a máquina,
faça compras ou envie mensagens/e-mails em nome do usuário DEVE passar
por este gate antes de ser executada — conforme exigido pela especificação
do projeto. A forma de perguntar (console, voz, GUI) é plugável via
`ConfirmationProvider`.
"""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass

from config.schema import SecurityConfig
from core.exceptions import ConfirmationDenied, ConfirmationTimeout
from core.logger import get_logger
from security.permissions import registry as permission_registry

logger = get_logger("confirmation")


@dataclass
class DestructiveAction:
    """Descreve uma ação que requer confirmação explícita do usuário."""

    key: str  # ex.: "delete_files"
    description: str  # ex.: "Apagar 12 arquivos em Downloads (230 MB)"


class ConfirmationProvider(ABC):
    """Interface para qualquer forma de pedir confirmação ao usuário."""

    @abstractmethod
    async def ask(self, action: DestructiveAction) -> bool:
        """Retorna True se o usuário confirmou a ação."""


class ConsoleConfirmationProvider(ConfirmationProvider):
    """Implementação via terminal — usada até as Fases 4/5 (voz/GUI) chegarem."""

    async def ask(self, action: DestructiveAction) -> bool:
        prompt = f"\n⚠️  Confirmar ação destrutiva: {action.description}\nContinuar? [s/N]: "
        response = await asyncio.to_thread(input, prompt)
        return response.strip().lower() in ("s", "sim", "y", "yes")


class ConfirmationGate:
    """Ponto único por onde toda ação destrutiva deve passar."""

    def __init__(self, config: SecurityConfig, provider: ConfirmationProvider) -> None:
        self._config = config
        self._provider = provider

    async def confirm(self, action: DestructiveAction) -> None:
        """Levanta `ConfirmationDenied`/`ConfirmationTimeout` se não for confirmada.

        Se `action.key` não estiver em `require_confirmation_for`, a ação
        passa direto — permite configurar quais categorias exigem confirmação.
        """
        # warn if action is not registered in permission registry
        if action.key not in [p.key for p in permission_registry.list()]:
            logger.warning("Ação '%s' não registrada em security.permissions.registry", action.key)

        if action.key not in self._config.require_confirmation_for:
            return

        try:
            confirmed = await asyncio.wait_for(
                self._provider.ask(action),
                timeout=self._config.confirmation_timeout_seconds,
            )
        except asyncio.TimeoutError as exc:
            logger.warning("Confirmação expirou para ação '%s'", action.key)
            raise ConfirmationTimeout(action.key) from exc

        if not confirmed:
            logger.info("Usuário negou a ação destrutiva '%s'", action.key)
            raise ConfirmationDenied(action.key)

        logger.info("Ação destrutiva '%s' confirmada pelo usuário", action.key)
