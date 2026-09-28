import os
import threading
import shutil
import urllib.parse

from core.plugin_loader import Plugin
from core.event_bus import Event
from core.logger import get_logger

import security.manager as security_manager

logger = get_logger("plugin.open_app")


class OpenAppPlugin(Plugin):
    name = "open_app_action"
    version = "0.1.0"
    description = "Plugin simples para abrir aplicações a partir de mensagens do usuário"

    def setup(self, event_bus) -> None:
        self._event_bus = event_bus
        event_bus.subscribe("user_message", self._on_user_message)

    def _on_user_message(self, event: Event) -> None:
        try:
            payload = event.payload or {}
            text = (payload.get("text") or "").strip().lower()
            if not text:
                return

            prefix = self._match_open_prefix(text)
            if not prefix:
                return

            target = text[len(prefix) :].strip()
            if not target:
                self._event_bus.publish_sync(
                    Event(
                        name="system_message",
                        payload={"text": "Diga algo como 'abrir chrome' ou 'abrir documentos'."},
                        source="jarvis",
                    )
                )
                return

            if security_manager.manager and not security_manager.manager.is_allowed("automation.open_app"):
                logger.info("Ação bloqueada por política: automation.open_app")
                self._event_bus.publish_sync(
                    Event(name="system_message", payload={"text": "Ação de abrir aplicações bloqueada pela política."}, source="jarvis")
                )
                return

            site_command = "site" in prefix
            exe = self._resolve_executable(target, site_command=site_command)
            if not exe:
                logger.info("Executável não encontrado para: %s", target)
                self._event_bus.publish_sync(
                    Event(name="system_message", payload={"text": f"Não encontrei aplicativo, pasta ou site para '{target}'."}, source="jarvis")
                )
                return

            threading.Thread(target=self._run_open, args=(exe,), daemon=True).start()

        except Exception:
            logger.exception("Erro no handler de open_app_action")

    def _match_open_prefix(self, text: str) -> str | None:
        prefixes = [
            "abrir o site ",
            "abrir a site ",
            "abrir o ",
            "abrir a ",
            "abrir site ",
            "abrir ",
            "abra o site ",
            "abra a site ",
            "abra o ",
            "abra a ",
            "abra site ",
            "abra ",
            "abre o site ",
            "abre a site ",
            "abre o ",
            "abre a ",
            "abre site ",
            "abre ",
        ]
        for prefix in prefixes:
            if text.startswith(prefix):
                return prefix
        return None

    def _resolve_executable(self, target: str, site_command: bool = False) -> str | None:
        normalized = target.lower().strip()

        if os.path.exists(target):
            return target

        if "\\:" in target or target.startswith("\\"):
            candidate = os.path.expandvars(target)
            return candidate if os.path.exists(candidate) else None

        if site_command:
            return self._normalize_url(target)

        if self._looks_like_url(normalized):
            return self._normalize_url(target)
        if "notepad" in normalized or "bloco" in normalized or "bloco de notas" in normalized:
            return "notepad.exe"
        if "calculadora" in normalized or normalized == "calc":
            return shutil.which("calc")
        if "paint" in normalized or "paintbrush" in normalized:
            return shutil.which("mspaint")
        if "chrome" in normalized or "navegador" in normalized or "internet" in normalized:
            return self._find_chrome()
        if "edge" in normalized:
            return shutil.which("msedge") or shutil.which("edge")
        if any(keyword in normalized for keyword in ("documentos", "desktop", "downloads", "área de trabalho", "pasta", "meu pc", "este pc", "explorador")):
            folder = self._find_folder(normalized)
            if folder:
                return folder
            return shutil.which("explorer")
        if "prompt" in normalized or "cmd" in normalized or "powershell" in normalized:
            return shutil.which("cmd") or shutil.which("powershell")
        if "word" in normalized or "office" in normalized:
            return shutil.which("winword")
        if "excel" in normalized:
            return shutil.which("excel")
        if "code" in normalized or "visual studio" in normalized or "vscode" in normalized:
            return shutil.which("code")
        if "spotify" in normalized:
            return shutil.which("spotify")

        found = shutil.which(target)
        if found:
            return found

        return None

    def _find_chrome(self) -> str | None:
        paths = [
            os.path.join(os.environ.get("PROGRAMFILES", ""), "Google\\Chrome\\Application\\chrome.exe"),
            os.path.join(os.environ.get("PROGRAMFILES(X86)", ""), "Google\\Chrome\\Application\\chrome.exe"),
        ]
        for p in paths:
            if os.path.exists(p):
                return p
        return shutil.which("chrome") or shutil.which("chromium")

    def _find_folder(self, target: str) -> str | None:
        user = os.path.expandvars("%USERPROFILE%")
        if "documentos" in target:
            path = os.path.join(user, "Documents")
            return path if os.path.exists(path) else None
        if "desktop" in target or "area de trabalho" in target:
            path = os.path.join(user, "Desktop")
            return path if os.path.exists(path) else None
        if "downloads" in target:
            path = os.path.join(user, "Downloads")
            return path if os.path.exists(path) else None
        return None

    def _looks_like_url(self, target: str) -> bool:
        lower_target = target.lower()
        if lower_target.startswith(("http://", "https://", "www.")):
            return True
        if lower_target.endswith((".exe", ".bat", ".cmd", ".ps1", ".lnk", ".msc", ".txt", ".pdf", ".docx", ".xlsx", ".pptx")):
            return False
        if "." in target and " " not in target and not target.startswith(("c:", "c:/", "\\", "/")):
            return True
        return False

    def _normalize_url(self, target: str) -> str:
        lower_target = target.lower().strip()
        if lower_target.startswith(("http://", "https://")):
            return target
        if lower_target.startswith("www."):
            return f"https://{target}"
        if "." in target:
            return f"https://{target}"
        return f"https://www.{target}.com"

    def _run_open(self, exe: str) -> None:
        try:
            os.startfile(exe)
            logger.info("OpenAppPlugin abriu: %s", exe)
            self._event_bus.publish_sync(Event(name="system_message", payload={"text": f"Abri: {exe}"}, source="jarvis"))
        except Exception:
            logger.exception("Falha ao abrir: %s", exe)
            self._event_bus.publish_sync(Event(name="system_message", payload={"text": f"Não foi possível abrir: {exe}"}, source="jarvis"))
