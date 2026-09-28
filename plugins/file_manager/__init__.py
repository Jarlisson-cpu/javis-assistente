from pathlib import Path

from core.plugin_loader import Plugin
from core.event_bus import Event
from core.confirmation import DestructiveAction
from core.exceptions import ConfirmationDenied
from core.logger import get_logger
import security.manager as security_manager

logger = get_logger("plugin.file_manager")


def _get_project_root() -> Path:
    return Path.cwd()


class FileManagerPlugin(Plugin):
    name = "file_manager"
    version = "0.1.0"
    description = "Plugin para ler, criar e apagar arquivos dentro do projeto." 

    def setup(self, event_bus) -> None:
        self._event_bus = event_bus
        self._confirmation = getattr(event_bus, "confirmation_gate", None)
        event_bus.subscribe("user_message", self._on_user_message)

    async def _on_user_message(self, event: Event) -> None:
        payload = event.payload or {}
        text = (payload.get("text") or "").strip().lower()

        if text.startswith("ler arquivo "):
            self._read_file(text[len("ler arquivo "):].strip())
        elif text.startswith("criar arquivo "):
            self._write_file_request(text[len("criar arquivo "):].strip())
        elif text.startswith("apagar arquivo "):
            await self._delete_file(text[len("apagar arquivo "):].strip())

    def _normalize_path(self, path: str) -> Path | None:
        project_root = _get_project_root()
        target = project_root / path
        try:
            resolved = target.resolve()
        except Exception:
            return None
        if project_root not in resolved.parents and resolved != project_root:
            return None
        return resolved

    def _publish_system(self, message: str) -> None:
        self._event_bus.publish_sync(Event(name="system_message", payload={"text": message}, source="jarvis"))

    def _read_file(self, path: str) -> None:
        if security_manager.manager and not security_manager.manager.is_allowed("file.read"):
            self._publish_system("Leitura de arquivos bloqueada pela política.")
            return

        file_path = self._normalize_path(path)
        if not file_path or not file_path.exists():
            self._publish_system(f"Arquivo não encontrado: {path}")
            return

        try:
            with file_path.open("r", encoding="utf-8") as f:
                content = f.read(2000)
            self._publish_system(f"Conteúdo de {path}:\n{content}")
        except Exception:
            logger.exception("Erro ao ler arquivo %s", path)
            self._publish_system(f"Falha ao ler o arquivo: {path}")

    def _write_file_request(self, rest: str) -> None:
        if security_manager.manager and not security_manager.manager.is_allowed("file.write"):
            self._publish_system("Escrita de arquivos bloqueada pela política.")
            return

        if ":" not in rest:
            self._publish_system("Use 'criar arquivo <caminho> : <texto>' para criar ou atualizar um arquivo.")
            return

        path_part, text_part = rest.split(":", 1)
        file_path = self._normalize_path(path_part.strip())
        if not file_path:
            self._publish_system(f"Caminho inválido: {path_part}")
            return

        try:
            file_path.parent.mkdir(parents=True, exist_ok=True)
            with file_path.open("w", encoding="utf-8") as f:
                f.write(text_part.strip())
            self._publish_system(f"Arquivo salvo: {path_part}")
        except Exception:
            logger.exception("Erro ao escrever arquivo %s", path_part)
            self._publish_system(f"Falha ao salvar o arquivo: {path_part}")

    async def _delete_file(self, path: str) -> None:
        if security_manager.manager and not security_manager.manager.is_allowed("file.delete"):
            self._publish_system("Exclusão de arquivos bloqueada pela política.")
            return

        file_path = self._normalize_path(path)
        if not file_path or not file_path.exists():
            self._publish_system(f"Arquivo não encontrado: {path}")
            return

        try:
            if self._confirmation is None:
                self._publish_system("Exclusão cancelada: confirmação indisponível.")
                return
            await self._confirmation.confirm(
                DestructiveAction(key="file.delete", description=f"Apagar o arquivo {path}")
            )
            file_path.unlink()
            self._publish_system(f"Arquivo apagado: {path}")
        except ConfirmationDenied:
            self._publish_system(f"Exclusão cancelada: {path}")
        except Exception:
            logger.exception("Erro ao apagar arquivo %s", path)
            self._publish_system(f"Falha ao apagar o arquivo: {path}")
