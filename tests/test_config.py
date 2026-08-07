"""Testes do carregamento e validação de configuração."""

from pathlib import Path

import pytest

from core.config import ConfigLoader
from core.exceptions import ConfigError


def test_load_valid_config(tmp_path: Path) -> None:
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        """
app:
  name: "JARVIS-Test"
logging:
  level: "DEBUG"
""",
        encoding="utf-8",
    )

    config = ConfigLoader(config_path=config_file, env_path=tmp_path / ".env").load()

    assert config.app.name == "JARVIS-Test"
    assert config.logging.level == "DEBUG"


def test_missing_config_raises(tmp_path: Path) -> None:
    loader = ConfigLoader(config_path=tmp_path / "does_not_exist.yaml")
    with pytest.raises(ConfigError):
        loader.load()


def test_invalid_yaml_raises(tmp_path: Path) -> None:
    config_file = tmp_path / "config.yaml"
    config_file.write_text("app: [unclosed", encoding="utf-8")

    with pytest.raises(ConfigError):
        ConfigLoader(config_path=config_file).load()
