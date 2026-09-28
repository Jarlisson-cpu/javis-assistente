import os
import asyncio
from pathlib import Path
from typing import Any

import pyautogui

from core.event_bus import Event
from core.confirmation import DestructiveAction
from core.logger import get_logger

logger = get_logger("automation")


class Automation:
    def __init__(self, core) -> None:
        self.core = core

    def _require_permission(self, key: str) -> None:
        permission_manager = getattr(self.core, "permission_manager", None)
        if permission_manager is None or not permission_manager.is_allowed(key):
            raise PermissionError(f"Ação bloqueada pela permissão {key}.")

    def open_application(self, path: str) -> None:
        self._require_permission("automation.open_app")
        try:
            os.startfile(path)
            logger.info("Abriu aplicação: %s", path)
        except Exception as exc:
            logger.exception("Falha ao abrir aplicação %s: %s", path, exc)

    def click(self, x: int, y: int) -> None:
        self._require_permission("automation.click")
        pyautogui.click(x, y)
        logger.info("Clique em (%s,%s)", x, y)

    def type_text(self, text: str, interval: float = 0.0) -> None:
        self._require_permission("automation.type_text")
        pyautogui.write(text, interval=interval)
        logger.info("Digitou texto: %s", text)

    def hotkey(self, *keys: str) -> None:
        self._require_permission("automation.hotkey")
        pyautogui.hotkey(*keys)
        logger.info("Hotkey pressionada: %s", keys)

    async def delete_file(self, path: str) -> None:
        self._require_permission("automation.delete_file")
        action = DestructiveAction(key="automation.delete_file", description=f"Apagar o arquivo {path}")
        await self.core.confirmation.confirm(action)
        try:
            Path(path).unlink()
            logger.info("Arquivo apagado: %s", path)
        except Exception:
            logger.exception("Erro ao apagar arquivo: %s", path)
