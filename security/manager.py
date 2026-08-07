from __future__ import annotations

from typing import Dict
from core.logger import get_logger

logger = get_logger("permissions")


class PermissionManager:
    def __init__(self, mapping: Dict[str, bool] | None = None) -> None:
        self._map = mapping or {}

    def is_allowed(self, key: str) -> bool:
        if key in self._map:
            return bool(self._map[key])
        logger.debug("Permissão %s não definida explicitamente; permitindo por padrão", key)
        return True

    def set_permission(self, key: str, value: bool) -> None:
        self._map[key] = bool(value)
        logger.info("Permissão definida: %s = %s", key, value)

    def list_permissions(self) -> Dict[str, bool]:
        return dict(self._map)


# singleton instance set by core
manager: PermissionManager | None = None
