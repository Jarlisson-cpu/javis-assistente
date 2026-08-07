"""Hierarquia de exceções do núcleo do JARVIS."""

from __future__ import annotations


class JarvisError(Exception):
    """Exceção base para todos os erros do JARVIS."""


class ConfigError(JarvisError):
    """Erro ao carregar ou validar a configuração."""


class PluginError(JarvisError):
    """Erro ao carregar, iniciar ou executar um plugin."""


class ConfirmationDenied(JarvisError):
    """Levantada quando uma ação destrutiva não foi confirmada pelo usuário."""

    def __init__(self, action_name: str) -> None:
        self.action_name = action_name
        super().__init__(f"Ação destrutiva negada ou não confirmada: {action_name}")


class ConfirmationTimeout(ConfirmationDenied):
    """Levantada quando a confirmação expira sem resposta do usuário."""
