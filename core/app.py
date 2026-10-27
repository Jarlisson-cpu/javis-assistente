"""Ponto central que monta e conecta todos os subsistemas do núcleo."""

from __future__ import annotations

import os
import threading

import security.manager as security_manager_module
from core.config import ConfigLoader
from core.confirmation import ConfirmationGate, ConsoleConfirmationProvider
from core.event_bus import Event, EventBus
from core.logger import get_logger, setup_logging
from core.plugin_loader import PluginLoader
from memory import MemoryManager
from security.manager import PermissionManager
from skills import SkillExecutor, registry as skill_registry
from skills.router import SkillRouter
from users import SessionManager, User, UserError, UserStore
from users import context as user_context
from voice.manager import VoiceManager

logger = get_logger("app")


class JarvisCore:
    """Orquestra config, logging, event bus, plugins, usuários, skills e voz.

    Módulos (voice, ai, gui, automation...) recebem uma instância de
    `JarvisCore` e se conectam a ela via `event_bus` — nunca importando uns aos
    outros diretamente.
    """

    def __init__(self, config_path: str | None = None) -> None:
        self.config = ConfigLoader(config_path or os.getenv("JARVIS_CONFIG") or "config.yaml").load()
        setup_logging(self.config.logging)
        self._apply_ai_config()

        self.event_bus = EventBus()
        self.confirmation = ConfirmationGate(self.config.security, ConsoleConfirmationProvider())
        self.event_bus.confirmation_gate = self.confirmation
        self.plugin_loader = PluginLoader(self.config.plugins, self.event_bus)
        self.memory = MemoryManager(
            db_path=self.config.memory.db_path,
            vector_enabled=self.config.memory.vector_enabled,
            vector_path=self.config.memory.vector_path,
            vector_collection=self.config.memory.vector_collection,
            embedding_model=self.config.memory.embedding_model,
        )
        self.users = UserStore(self.config.memory.db_path)
        self.sessions = SessionManager(self.config.users.session_hours)

        try:
            self.voice: VoiceManager | None = VoiceManager(self.config.voice)
        except Exception:
            logger.exception("Módulo de voz indisponível")
            self.voice = None

        self.permission_manager = PermissionManager(
            self.config.security.permissions, persist_path=self.config.security.permissions_file
        )
        security_manager_module.manager = self.permission_manager

        # a interface web fala pelo navegador; nela o servidor fica em silêncio
        self.speak_responses = True
        self.skills = skill_registry
        self.skill_router = SkillRouter(self.skills, SkillExecutor(self.permission_manager, self.confirmation))

    def _apply_ai_config(self) -> None:
        """`config.yaml → ai` vira padrão para o AIManager (variáveis de ambiente têm prioridade)."""
        if self.config.ai.provider and self.config.ai.provider != "auto" and not os.getenv("JARVIS_AI_PROVIDER"):
            os.environ["JARVIS_AI_PROVIDER"] = self.config.ai.provider
        if self.config.ai.model and not os.getenv("JARVIS_AI_MODEL"):
            os.environ["JARVIS_AI_MODEL"] = self.config.ai.model

    # ------------------------------------------------------------------ usuários
    @property
    def current_user(self) -> User | None:
        return user_context.current_user()

    def default_local_user(self) -> User | None:
        """Usuário usado no terminal/voz/GUI quando nenhum foi informado."""
        if self.config.users.default_user:
            return self.users.get(self.config.users.default_user)
        users = self.users.list()
        if len(users) == 1:
            return users[0]
        return next((user for user in users if user.is_admin), None)

    def login(self, username: str, password: str | None = None) -> User:
        if password is None:
            user = self.users.get(username)
        else:
            user = self.users.authenticate(username, password)
        if user is None:
            raise UserError("Usuário ou senha inválidos.")
        user_context.set_current_user(user)
        logger.info("Usuário ativo: %s", user.username)
        return user

    # ------------------------------------------------------------------ inicialização
    def bootstrap(self) -> None:
        """Inicializa o núcleo: carrega plugins e sinaliza que está pronto."""
        logger.info("Iniciando %s v%s", self.config.app.name, self.config.app.version)
        # a mensagem do usuário é gravada antes de qualquer resposta (ordem correta no histórico)
        self.event_bus.subscribe("user_message", self._persist)
        self.event_bus.subscribe("system_message", self._persist)
        # o roteador de skills vem antes dos plugins para responder primeiro
        self.skill_router.attach(self.event_bus)
        plugins = self.plugin_loader.load_all()
        for plugin in plugins:
            attach = getattr(plugin, "attach_core", None)
            if callable(attach):
                attach(self)
        logger.info("%d plugin(s) e %d comando(s) carregados", len(plugins), len(self.skills.list()))

        if self.voice:
            self.event_bus.subscribe("system_message", self._speak_system_message)
        logger.info("Núcleo pronto.")

    def _persist(self, event: Event) -> None:
        try:
            payload = event.payload or {}
            text = payload.get("text", "")
            source = event.source or "unknown"
            username = payload.get("username") or (self.current_user.username if self.current_user else None)
            if self.memory.vector_memory is None:
                self.memory.add_message(source, text, username=username)  # SQLite: rápido e mantém a ordem
            else:
                # indexação vetorial gera embeddings; não segura o assistente esperando
                threading.Thread(
                    target=self.memory.add_message, args=(source, text), kwargs={"username": username}, daemon=True
                ).start()
        except Exception:
            logger.exception("Falha ao persistir mensagem")

    def _speak_system_message(self, event: Event) -> None:
        try:
            if not self.speak_responses or not self.permission_manager.is_allowed("voice.tts"):
                return
            payload = event.payload or {}
            text = payload.get("text", "")
            if text and not payload.get("silent"):
                self.voice.speak(text)
        except Exception:
            logger.exception("Falha ao reproduzir voz para system_message")

    def shutdown(self) -> None:
        for plugin in list(self.plugin_loader.loaded.values()):
            try:
                plugin.teardown()
            except Exception:
                logger.exception("Falha ao desligar plugin %s", plugin.name)
