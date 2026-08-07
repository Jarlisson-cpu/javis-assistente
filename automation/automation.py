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

    def open_application(self, path: str) -> None:
        try:
            os.startfile(path)
            logger.info("Abriu aplicação: %s", path)
        except Exception as exc:
            logger.exception("Falha ao abrir aplicação %s: %s", path, exc)

    def click(self, x: int, y: int) -> None:
        pyautogui.click(x, y)
        logger.info("Clique em (%s,%s)", x, y)

    def type_text(self, text: str, interval: float = 0.0) -> None:
        pyautogui.write(text, interval=interval)
        logger.info("Digitou texto: %s", text)

    def hotkey(self, *keys: str) -> None:
        pyautogui.hotkey(*keys)
        logger.info("Hotkey pressionada: %s", keys)

    async def delete_file(self, path: str) -> None:
        action = DestructiveAction(key="automation.delete_file", description=f"Apagar o arquivo {path}")
        await self.core.confirmation.confirm(action)
        try:
            Path(path).unlink()
            logger.info("Arquivo apagado: %s", path)
        except Exception:
            logger.exception("Erro ao apagar arquivo: %s", path)
