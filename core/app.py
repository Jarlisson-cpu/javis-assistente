"""Ponto central que monta e conecta todos os subsistemas do núcleo."""

from __future__ import annotations

from core.config import ConfigLoader
from core.confirmation import ConfirmationGate, ConsoleConfirmationProvider
from core.event_bus import EventBus
from core.logger import get_logger, setup_logging
from core.plugin_loader import PluginLoader
import threading
from memory import MemoryManager
from voice.manager import VoiceManager
from security.manager import PermissionManager, manager as global_permission_manager

logger = get_logger("app")


class JarvisCore:
    """Orquestra config, logging, event bus, plugins e o gate de confirmação.

    Módulos futuros (voice, ai, gui, automation...) recebem uma instância
    de `JarvisCore` e se conectam a ela via `event_bus` — nunca importando
    uns aos outros diretamente.
    """

    def __init__(self, config_path: str = "config.yaml") -> None:
        self.config = ConfigLoader(config_path).load()
        setup_logging(self.config.logging)

        self.event_bus = EventBus()
        self.confirmation = ConfirmationGate(self.config.security, ConsoleConfirmationProvider())
        self.event_bus.confirmation_gate = self.confirmation
        self.plugin_loader = PluginLoader(self.config.plugins, self.event_bus)
        # memory store
        self.memory = MemoryManager(
            db_path=self.config.memory.db_path,
            vector_enabled=self.config.memory.vector_enabled,
            vector_path=self.config.memory.vector_path,
            vector_collection=self.config.memory.vector_collection,
            embedding_model=self.config.memory.embedding_model,
        )
        # voice manager (optional)
        try:
            self.voice = VoiceManager(self.config.voice)
        except Exception:
            self.voice = None
        # permission manager (singleton)
        try:
            pm = PermissionManager(getattr(self.config.security, "permissions", {}))
            # set global
            import security.manager as _sm

            _sm.manager = pm
            self.permission_manager = pm
        except Exception:
            self.permission_manager = None

    def bootstrap(self) -> None:
        """Inicializa o núcleo: carrega plugins e sinaliza que está pronto."""
        logger.info("Iniciando %s v%s", self.config.app.name, self.config.app.version)
        plugins = self.plugin_loader.load_all()
        logger.info("%d plugin(s) carregado(s)", len(plugins))
        logger.info("Núcleo pronto.")
        # subscribe to user messages to persist history
        def _persist(event):
            try:
                payload = event.payload or {}
                text = payload.get("text", "")
                source = event.source or "unknown"
                # store async-safe via thread
                threading.Thread(target=self.memory.add_message, args=(source, text), daemon=True).start()
            except Exception:
                logger.exception("Falha ao persistir mensagem")

        self.event_bus.subscribe("user_message", _persist)
        self.event_bus.subscribe("system_message", _persist)

        if self.voice:
            self.event_bus.subscribe("system_message", self._speak_system_message)

    def _speak_system_message(self, event) -> None:
        try:
            if not self.permission_manager or not self.permission_manager.is_allowed("voice.tts"):
                return
            payload = event.payload or {}
            text = payload.get("text", "")
            if text:
                threading.Thread(target=self.voice.speak, args=(text,), daemon=True).start()
        except Exception:
            logger.exception("Falha ao reproduzir voz para system_message")
