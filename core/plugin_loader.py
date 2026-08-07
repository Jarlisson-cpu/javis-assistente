"""Descoberta e carregamento dinâmico de plugins.

Qualquer pasta dentro de `plugins/` contendo uma classe que implemente
`Plugin` é carregada automaticamente — nenhum registro manual é necessário,
conforme a exigência de "adicionar apenas uma pasta" do projeto.
"""

from __future__ import annotations

import importlib
import inspect
import pkgutil
from abc import ABC, abstractmethod
from pathlib import Path

from config.schema import PluginsConfig
from core.event_bus import EventBus
from core.exceptions import PluginError
from core.logger import get_logger

logger = get_logger("plugin_loader")


class Plugin(ABC):
    """Interface que todo plugin do JARVIS deve implementar."""

    name: str = "unnamed_plugin"
    version: str = "0.1.0"
    description: str = ""

    @abstractmethod
    def setup(self, event_bus: EventBus) -> None:
        """Chamado uma vez ao carregar o plugin — registre handlers de evento aqui."""

    def teardown(self) -> None:  # noqa: B027 - hook opcional
        """Chamado ao desligar o JARVIS. Sobrescreva se precisar liberar recursos."""


class PluginLoader:
    """Descobre e instancia plugins a partir do diretório configurado."""

    def __init__(self, config: PluginsConfig, event_bus: EventBus) -> None:
        self._config = config
        self._event_bus = event_bus
        self.loaded: dict[str, Plugin] = {}

    def load_all(self) -> list[Plugin]:
        """Descobre, filtra e inicializa todos os plugins válidos."""
        if not self._config.autoload:
            logger.info("Autoload de plugins desabilitado na configuração")
            return []

        plugins_dir = Path(self._config.directory)
        if not plugins_dir.exists():
            logger.warning("Diretório de plugins não encontrado: %s", plugins_dir)
            return []

        for module_info in pkgutil.iter_modules([str(plugins_dir)]):
            plugin_name = module_info.name

            if self._config.disabled and plugin_name in self._config.disabled:
                continue
            if self._config.enabled and plugin_name not in self._config.enabled:
                continue

            self._load_plugin(plugins_dir, plugin_name)

        return list(self.loaded.values())

    def _load_plugin(self, plugins_dir: Path, plugin_name: str) -> None:
        module_path = f"{plugins_dir.name}.{plugin_name}"
        try:
            module = importlib.import_module(module_path)
        except ImportError as exc:
            raise PluginError(f"Falha ao importar plugin '{plugin_name}': {exc}") from exc

        plugin_classes = [
            obj
            for _, obj in inspect.getmembers(module, inspect.isclass)
            if issubclass(obj, Plugin) and obj is not Plugin
        ]

        if not plugin_classes:
            logger.warning("Nenhuma classe Plugin encontrada em '%s'", plugin_name)
            return

        for plugin_cls in plugin_classes:
            instance = plugin_cls()
            instance.setup(self._event_bus)
            self.loaded[instance.name] = instance
            logger.info("Plugin carregado: %s v%s", instance.name, instance.version)
