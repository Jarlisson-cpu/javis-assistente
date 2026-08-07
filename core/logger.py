"""Configuração centralizada de logging do JARVIS.

Todos os módulos devem obter seu logger via `get_logger(__name__)` em vez
de configurar `logging` diretamente, garantindo formato e destino únicos.
"""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from config.schema import LoggingConfig

_CONFIGURED = False


def setup_logging(config: LoggingConfig) -> None:
    """Configura o logger raiz uma única vez, com base na configuração."""
    global _CONFIGURED
    if _CONFIGURED:
        return

    log_dir = Path(config.directory)
    log_dir.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger("jarvis")
    root.setLevel(config.level)

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler = RotatingFileHandler(
        log_dir / "jarvis.log",
        maxBytes=config.max_file_size_mb * 1024 * 1024,
        backupCount=config.backup_count,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)

    if config.console_output:
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        root.addHandler(console_handler)

    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    """Retorna um logger filho do logger raiz `jarvis`."""
    return logging.getLogger(f"jarvis.{name}")
