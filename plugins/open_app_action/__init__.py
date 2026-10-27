"""Abre aplicativos, pastas, sites e telas de configuração do Windows.

"abre o spotify", "abrir youtube", "abra as configurações de bluetooth",
"abre a pasta downloads", "abrir site github.com". Aplicativos são encontrados
por apelidos conhecidos, pelo PATH e pela lista do Menu Iniciar (`Get-StartApps`),
que inclui apps da Microsoft Store.
"""

import difflib
import json
import os
import shutil
import subprocess
import threading

import security.manager as security_manager
from core.event_bus import Event
from core.logger import get_logger
from core.plugin_loader import Plugin
from core.text import strip_accents
from skills import registry as skill_registry

logger = get_logger("plugin.open_app")

KNOWN_SITES = {
    "google": "https://www.google.com",
    "youtube": "https://www.youtube.com",
    "youtube music": "https://music.youtube.com",
    "gmail": "https://mail.google.com",
    "email": "https://mail.google.com",
    "e-mail": "https://mail.google.com",
    "drive": "https://drive.google.com",
    "google drive": "https://drive.google.com",
    "agenda": "https://calendar.google.com",
    "calendario": "https://calendar.google.com",
    "maps": "https://maps.google.com",
    "mapa": "https://maps.google.com",
    "tradutor": "https://translate.google.com",
    "whatsapp web": "https://web.whatsapp.com",
    "instagram": "https://www.instagram.com",
    "facebook": "https://www.facebook.com",
    "twitter": "https://x.com",
    "x": "https://x.com",
    "linkedin": "https://www.linkedin.com",
    "github": "https://github.com",
    "netflix": "https://www.netflix.com",
    "twitch": "https://www.twitch.tv",
    "chatgpt": "https://chatgpt.com",
    "claude": "https://claude.ai",
    "outlook": "https://outlook.live.com",
    "wikipedia": "https://pt.wikipedia.org",
    "amazon": "https://www.amazon.com.br",
    "mercado livre": "https://www.mercadolivre.com.br",
}

SETTINGS_PAGES = {
    "wifi": "ms-settings:network-wifi",
    "wi fi": "ms-settings:network-wifi",
    "rede": "ms-settings:network-status",
    "internet": "ms-settings:network-status",
    "bluetooth": "ms-settings:bluetooth",
    "som": "ms-settings:sound",
    "audio": "ms-settings:sound",
    "tela": "ms-settings:display",
    "video": "ms-settings:display",
    "monitor": "ms-settings:display",
    "energia": "ms-settings:powersleep",
    "bateria": "ms-settings:batterysaver",
    "atualiza": "ms-settings:windowsupdate",
    "windows update": "ms-settings:windowsupdate",
    "aplicativos": "ms-settings:appsfeatures",
    "apps": "ms-settings:appsfeatures",
    "notifica": "ms-settings:notifications",
    "privacidade": "ms-settings:privacy",
    "conta": "ms-settings:yourinfo",
    "mouse": "ms-settings:mousetouchpad",
    "touchpad": "ms-settings:devices-touchpad",
    "teclado": "ms-settings:typing",
    "impressora": "ms-settings:printers",
    "papel de parede": "ms-settings:personalization-background",
    "plano de fundo": "ms-settings:personalization-background",
    "personaliza": "ms-settings:personalization",
    "armazenamento": "ms-settings:storagesense",
    "data": "ms-settings:dateandtime",
    "hora": "ms-settings:dateandtime",
    "idioma": "ms-settings:regionlanguage",
}

_PREFIXES = [
    f"{verb} {article}"
    for verb in ("abrir", "abra", "abre", "abri", "inicia", "iniciar", "inicie", "executa", "executar", "execute", "liga", "ligar", "ligue")
    for article in ("o site ", "a site ", "site ", "o aplicativo ", "o app ", "o programa ", "a pasta ", "as ", "os ", "o ", "a ", "")
]


class OpenAppPlugin(Plugin):
    name = "open_app_action"
    version = "1.0.0"
    description = "Abre aplicativos (inclusive da Microsoft Store), pastas, sites e configurações do Windows."

    _start_apps_cache: list[tuple[str, str]] | None = None
    _start_apps_lock = threading.Lock()

    def setup(self, event_bus) -> None:
        self._event_bus = event_bus
        event_bus.subscribe("user_message", self._on_user_message)

    def _reply(self, text: str) -> None:
        self._event_bus.publish_sync(Event(name="system_message", payload={"text": text}, source="jarvis"))

    def _on_user_message(self, event: Event) -> None:
        try:
            payload = event.payload or {}
            text = (payload.get("text") or "").strip().lower()
            if not text or skill_registry.match(text) is not None:
                return

            prefix = self._match_open_prefix(text)
            if not prefix:
                return

            target = text[len(prefix) :].strip(" .,!?")
            if not target:
                self._reply("Diga algo como 'abrir chrome', 'abrir youtube' ou 'abrir documentos'.")
                return

            if security_manager.manager and not security_manager.manager.is_allowed("automation.open_app"):
                logger.info("Ação bloqueada por política: automation.open_app")
                self._reply("Ação de abrir aplicações bloqueada pela política.")
                return

            site_command = "site" in prefix
            exe = self._resolve_executable(target, site_command=site_command)
            if not exe:
                logger.info("Executável não encontrado para: %s", target)
                self._reply(f"Não encontrei aplicativo, pasta ou site para '{target}'.")
                return

            threading.Thread(target=self._run_open, args=(exe, target), daemon=True).start()

        except Exception:
            logger.exception("Erro no handler de open_app_action")

    def _match_open_prefix(self, text: str) -> str | None:
        for prefix in sorted(_PREFIXES, key=len, reverse=True):
            if prefix and text.startswith(prefix):
                # "liga o computador"/"executa o comando" pertencem a outras skills
                if prefix.startswith(("liga", "executa", "execute")) and not prefix.endswith(("app ", "programa ", "aplicativo ")):
                    continue
                return prefix
        return None

    def _resolve_executable(self, target: str, site_command: bool = False) -> str | None:
        normalized = strip_accents(target.lower().strip())

        if os.path.exists(target):
            return target

        if "\\:" in target or target.startswith("\\"):
            candidate = os.path.expandvars(target)
            return candidate if os.path.exists(candidate) else None

        if site_command:
            return KNOWN_SITES.get(normalized) or self._normalize_url(target)

        if self._looks_like_url(normalized):
            return self._normalize_url(target)

        if "configurac" in normalized or "ajustes" in normalized:
            return self._settings_page(normalized)

        if "notepad" in normalized or "bloco" in normalized or "bloco de notas" in normalized:
            return "notepad.exe"
        if "calculadora" in normalized or normalized == "calc":
            return shutil.which("calc")
        if "paint" in normalized or "paintbrush" in normalized:
            return shutil.which("mspaint")
        if "chrome" in normalized or "navegador" in normalized or normalized == "internet":
            return self._find_chrome()
        if "edge" in normalized:
            return shutil.which("msedge") or shutil.which("edge")
        if any(keyword in normalized for keyword in ("documentos", "desktop", "downloads", "area de trabalho", "imagens", "musicas", "videos", "pasta", "meu pc", "este pc", "explorador", "arquivos")):
            folder = self._find_folder(normalized)
            if folder:
                return folder
            return shutil.which("explorer")
        if "prompt" in normalized or normalized == "cmd" or "powershell" in normalized or "terminal" in normalized:
            return shutil.which("wt") or shutil.which("powershell") or shutil.which("cmd")
        if normalized in ("word", "office") or "microsoft word" in normalized:
            return shutil.which("winword") or self._find_start_app("word")
        if "excel" in normalized:
            return shutil.which("excel") or self._find_start_app("excel")
        if normalized in ("code", "vscode", "vs code") or "visual studio code" in normalized:
            return shutil.which("code") or self._find_start_app("visual studio code")

        if normalized in KNOWN_SITES:
            return KNOWN_SITES[normalized]

        found = shutil.which(target)
        if found:
            return found

        app = self._find_start_app(normalized)
        if app:
            return app
        if normalized == "whatsapp":
            return KNOWN_SITES["whatsapp web"]
        return None

    def _settings_page(self, normalized: str) -> str:
        for keyword, uri in SETTINGS_PAGES.items():
            if keyword in normalized:
                return uri
        return "ms-settings:"

    @classmethod
    def _load_start_apps(cls) -> list[tuple[str, str]]:
        with cls._start_apps_lock:
            if cls._start_apps_cache is not None:
                return cls._start_apps_cache
            apps: list[tuple[str, str]] = []
            if os.name == "nt":
                try:
                    result = subprocess.run(
                        ["powershell", "-NoProfile", "-NonInteractive", "-Command", "Get-StartApps | ConvertTo-Json -Compress"],
                        capture_output=True,
                        text=True,
                        timeout=20,
                        encoding="utf-8",
                        errors="replace",
                        creationflags=0x08000000,
                    )
                    data = json.loads(result.stdout or "[]")
                    if isinstance(data, dict):
                        data = [data]
                    apps = [(str(item["Name"]), str(item["AppID"])) for item in data if item.get("Name") and item.get("AppID")]
                except (OSError, ValueError, subprocess.SubprocessError):
                    logger.warning("Não consegui listar os apps do Menu Iniciar")
            cls._start_apps_cache = apps
            return apps

    def _find_start_app(self, normalized: str) -> str | None:
        apps = self._load_start_apps()
        if not apps:
            return None
        names = {strip_accents(name.lower()): app_id for name, app_id in apps}
        app_id = names.get(normalized)
        if app_id is None:
            starts = [name for name in names if name.startswith(normalized) or normalized in name.split()]
            if starts:
                app_id = names[min(starts, key=len)]
        if app_id is None:
            close = difflib.get_close_matches(normalized, list(names), n=1, cutoff=0.75)
            app_id = names[close[0]] if close else None
        if app_id is None:
            return None
        return app_id if os.path.isabs(app_id) or "://" in app_id else f"shell:AppsFolder\\{app_id}"

    def _find_chrome(self) -> str | None:
        paths = [
            os.path.join(os.environ.get("PROGRAMFILES", ""), "Google\\Chrome\\Application\\chrome.exe"),
            os.path.join(os.environ.get("PROGRAMFILES(X86)", ""), "Google\\Chrome\\Application\\chrome.exe"),
            os.path.join(os.environ.get("LOCALAPPDATA", ""), "Google\\Chrome\\Application\\chrome.exe"),
        ]
        for p in paths:
            if os.path.exists(p):
                return p
        return shutil.which("chrome") or shutil.which("chromium") or shutil.which("msedge")

    def _find_folder(self, target: str) -> str | None:
        user = os.path.expandvars("%USERPROFILE%")
        folders = (
            ("documentos", "Documents"),
            ("desktop", "Desktop"),
            ("area de trabalho", "Desktop"),
            ("downloads", "Downloads"),
            ("imagens", "Pictures"),
            ("musicas", "Music"),
            ("videos", "Videos"),
        )
        for keyword, folder in folders:
            if keyword in target:
                path = os.path.join(user, folder)
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

    def _run_open(self, exe: str, label: str | None = None) -> None:
        try:
            os.startfile(exe)
            logger.info("OpenAppPlugin abriu: %s", exe)
            self._reply(f"Abrindo {label or exe}.")
        except Exception:
            logger.exception("Falha ao abrir: %s", exe)
            self._reply(f"Não foi possível abrir {label or exe}.")
