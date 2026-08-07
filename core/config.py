"""Carregamento e validação da configuração central do JARVIS.

Lê `config.yaml` (configurações não sensíveis) e variáveis de ambiente /
`.env` (segredos, como chaves de API), retornando um objeto `RootConfig`
validado por Pydantic.
"""

from __future__ import annotations

import os
from pathlib import Path

import yaml
from dotenv import load_dotenv
from pydantic import ValidationError

from config.schema import RootConfig
from core.exceptions import ConfigError


class ConfigLoader:
    """Responsável por carregar e validar a configuração da aplicação."""

    def __init__(
        self, config_path: str | Path = "config.yaml", env_path: str | Path = ".env"
    ) -> None:
        self.config_path = Path(config_path)
        self.env_path = Path(env_path)

    def load(self) -> RootConfig:
        """Carrega `config.yaml` + `.env` e retorna a configuração validada.

        Raises:
            ConfigError: se o arquivo não existir ou o conteúdo for inválido.
        """
        if self.env_path.exists():
            load_dotenv(self.env_path)

        if not self.config_path.exists():
            raise ConfigError(f"Arquivo de configuração não encontrado: {self.config_path}")

        try:
            raw = yaml.safe_load(self.config_path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as exc:
            raise ConfigError(f"YAML inválido em {self.config_path}: {exc}") from exc

        try:
            return RootConfig.model_validate(raw)
        except ValidationError as exc:
            raise ConfigError(f"Configuração inválida: {exc}") from exc

    @staticmethod
    def get_secret(key: str) -> str | None:
        """Lê um segredo (ex.: chave de API) das variáveis de ambiente."""
        return os.environ.get(key)
