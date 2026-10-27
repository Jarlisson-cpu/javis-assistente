from __future__ import annotations

import json
from pathlib import Path
from typing import Dict

from core.logger import get_logger
from security.permissions import registry as permission_registry

logger = get_logger("permissions")


class PermissionManager:
    """Decide se uma ação é permitida.

    Ordem de decisão: valor salvo pelo usuário (GUI/web) → valor de
    `config.yaml` → padrão declarado no registro de permissões → permitido.
    Quando `persist_path` é informado, alterações feitas em tempo de execução
    sobrevivem ao reinício.
    """

    def __init__(self, mapping: Dict[str, bool] | None = None, persist_path: str | Path | None = None) -> None:
        self._map = dict(mapping or {})
        self._persist_path = Path(persist_path) if persist_path else None
        if self._persist_path and self._persist_path.is_file():
            try:
                saved = json.loads(self._persist_path.read_text(encoding="utf-8"))
                self._map.update({key: bool(value) for key, value in saved.items()})
            except (OSError, ValueError, AttributeError):
                logger.warning("Não consegui ler permissões salvas em %s", self._persist_path)

    def is_allowed(self, key: str) -> bool:
        if key in self._map:
            return bool(self._map[key])
        permission = permission_registry.get(key)
        if permission is not None:
            return permission.default
        logger.debug("Permissão %s não definida explicitamente; permitindo por padrão", key)
        return True

    def set_permission(self, key: str, value: bool) -> None:
        self._map[key] = bool(value)
        logger.info("Permissão definida: %s = %s", key, value)
        self._save()

    def list_permissions(self) -> Dict[str, bool]:
        values = {permission.key: self.is_allowed(permission.key) for permission in permission_registry.list()}
        values.update(self._map)
        return values

    def _save(self) -> None:
        if not self._persist_path:
            return
        try:
            self._persist_path.parent.mkdir(parents=True, exist_ok=True)
            self._persist_path.write_text(json.dumps(self._map, indent=2, sort_keys=True), encoding="utf-8")
        except OSError:
            logger.exception("Falha ao salvar permissões em %s", self._persist_path)


# singleton instance set by core
manager: PermissionManager | None = None
