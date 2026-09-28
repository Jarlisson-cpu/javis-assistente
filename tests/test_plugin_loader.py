"""Testes do carregador de plugins, usando o plugin de exemplo do projeto."""

from config.schema import PluginsConfig
from core.event_bus import EventBus
from core.plugin_loader import PluginLoader


def test_loads_example_plugin() -> None:
    event_bus = EventBus()
    config = PluginsConfig(directory="plugins", autoload=True)

    loader = PluginLoader(config, event_bus)
    plugins = loader.load_all()

    names = [p.name for p in plugins]
    assert "example_greeting" in names
    assert "specialized_agents" in names
    assert "browser_reader" in names
    assert "vision_ocr" in names
    assert "communication_draft" in names
    assert "media_search" in names


def test_disabled_plugin_is_skipped() -> None:
    event_bus = EventBus()
    config = PluginsConfig(directory="plugins", autoload=True, disabled=["example_greeting"])

    loader = PluginLoader(config, event_bus)
    plugins = loader.load_all()

    assert "example_greeting" not in [p.name for p in plugins]
