"""Controle do notebook Windows: volume, brilho, energia, janelas, apps e status.

Cada operação usa APIs nativas do Windows (teclas virtuais, `user32`, WMI via
PowerShell, `shutdown.exe`, `taskkill`). As dependências de execução são
injetáveis (`run`, `send_key`, `hotkey`, `typer`) para que tudo seja testável
sem tocar no sistema real.
"""

from __future__ import annotations

import ctypes
import os
import platform
import re
import socket
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Callable, Sequence

from core.logger import get_logger
from media.manager import MediaManager

logger = get_logger("system")

CREATE_NO_WINDOW = 0x08000000
VOLUME_STEP_PERCENT = 2  # cada tecla de volume do Windows muda 2%
MAX_COMMAND_OUTPUT = 1500

Runner = Callable[[Sequence[str]], "subprocess.CompletedProcess[str]"]

# nomes falados → executáveis
APP_ALIASES: dict[str, list[str]] = {
    "chrome": ["chrome.exe"],
    "google chrome": ["chrome.exe"],
    "navegador": ["chrome.exe", "msedge.exe", "firefox.exe"],
    "edge": ["msedge.exe"],
    "firefox": ["firefox.exe"],
    "bloco de notas": ["notepad.exe"],
    "notepad": ["notepad.exe"],
    "calculadora": ["CalculatorApp.exe", "calc.exe"],
    "word": ["WINWORD.EXE"],
    "excel": ["EXCEL.EXE"],
    "powerpoint": ["POWERPNT.EXE"],
    "spotify": ["Spotify.exe"],
    "vscode": ["Code.exe"],
    "vs code": ["Code.exe"],
    "visual studio code": ["Code.exe"],
    "code": ["Code.exe"],
    "explorador": ["explorer.exe"],
    "discord": ["Discord.exe"],
    "whatsapp": ["WhatsApp.exe", "WhatsApp.Root.exe"],
    "teams": ["ms-teams.exe", "Teams.exe"],
    "paint": ["mspaint.exe"],
    "steam": ["steam.exe"],
    "obs": ["obs64.exe"],
    "telegram": ["Telegram.exe"],
}

KEY_NAMES: dict[str, str] = {
    "enter": "enter",
    "entrar": "enter",
    "esc": "esc",
    "escape": "esc",
    "espaco": "space",
    "tab": "tab",
    "backspace": "backspace",
    "apagar": "backspace",
    "delete": "delete",
    "deletar": "delete",
    "cima": "up",
    "seta para cima": "up",
    "baixo": "down",
    "seta para baixo": "down",
    "esquerda": "left",
    "seta para esquerda": "left",
    "direita": "right",
    "seta para direita": "right",
    "home": "home",
    "end": "end",
    "f5": "f5",
    "f11": "f11",
    "windows": "win",
    "page up": "pageup",
    "page down": "pagedown",
}

SHORTCUTS: dict[str, tuple[str, ...]] = {
    "copiar": ("ctrl", "c"),
    "colar": ("ctrl", "v"),
    "recortar": ("ctrl", "x"),
    "desfazer": ("ctrl", "z"),
    "refazer": ("ctrl", "y"),
    "salvar": ("ctrl", "s"),
    "selecionar tudo": ("ctrl", "a"),
    "nova aba": ("ctrl", "t"),
    "fechar aba": ("ctrl", "w"),
    "reabrir aba": ("ctrl", "shift", "t"),
    "proxima aba": ("ctrl", "tab"),
    "aba anterior": ("ctrl", "shift", "tab"),
    "atualizar pagina": ("f5",),
    "recarregar pagina": ("f5",),
    "voltar pagina": ("alt", "left"),
    "avancar pagina": ("alt", "right"),
    "tela cheia": ("f11",),
    "procurar na pagina": ("ctrl", "f"),
    "imprimir": ("ctrl", "p"),
    "nova janela": ("ctrl", "n"),
    "minimizar tudo": ("win", "d"),
    "mostrar area de trabalho": ("win", "d"),
    "trocar de janela": ("alt", "tab"),
    "fechar janela": ("alt", "f4"),
    "maximizar janela": ("win", "up"),
    "minimizar janela": ("win", "down"),
    "abrir gerenciador de tarefas": ("ctrl", "shift", "esc"),
    "gerenciador de tarefas": ("ctrl", "shift", "esc"),
    "configuracoes rapidas": ("win", "a"),
    "central de notificacoes": ("win", "n"),
    "emoji": ("win", "."),
    "ditado do windows": ("win", "h"),
    "lupa": ("win", "+"),
}


def _default_run(args: Sequence[str]) -> "subprocess.CompletedProcess[str]":
    return subprocess.run(
        list(args),
        capture_output=True,
        text=True,
        timeout=30,
        creationflags=CREATE_NO_WINDOW if os.name == "nt" else 0,
        encoding="utf-8",
        errors="replace",
    )


def _default_hotkey(*keys: str) -> None:
    import pyautogui

    pyautogui.hotkey(*keys)


def _default_typer(text: str) -> None:
    import pyautogui

    # pyautogui.write não digita acentos; colar pelo clipboard preserva o texto exato
    if text.isascii():
        pyautogui.write(text, interval=0.01)
        return
    previous = SystemController.read_clipboard_static()
    SystemController.write_clipboard_static(text)
    pyautogui.hotkey("ctrl", "v")
    time.sleep(0.2)
    if previous is not None:
        SystemController.write_clipboard_static(previous)


def _powershell(script: str) -> list[str]:
    return ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", script]


class SystemController:
    def __init__(
        self,
        run: Runner | None = None,
        media: MediaManager | None = None,
        hotkey: Callable[..., None] | None = None,
        typer: Callable[[str], None] | None = None,
        screenshot_dir: str | Path | None = None,
    ) -> None:
        self._run = run or _default_run
        self._media = media or MediaManager()
        self._hotkey = hotkey or _default_hotkey
        self._typer = typer or _default_typer
        self.screenshot_dir = Path(screenshot_dir) if screenshot_dir else Path.home() / "Pictures" / "Jarvis"

    # ------------------------------------------------------------------ volume / mídia
    def volume_up(self, percent: int | None = None) -> str:
        steps = max(1, (percent or 10) // VOLUME_STEP_PERCENT)
        for _ in range(steps):
            self._media.control("volume_up")
        return f"Aumentei o volume em {steps * VOLUME_STEP_PERCENT}%."

    def volume_down(self, percent: int | None = None) -> str:
        steps = max(1, (percent or 10) // VOLUME_STEP_PERCENT)
        for _ in range(steps):
            self._media.control("volume_down")
        return f"Diminuí o volume em {steps * VOLUME_STEP_PERCENT}%."

    def set_volume(self, percent: int) -> str:
        if not 0 <= percent <= 100:
            raise ValueError("O volume deve ficar entre 0 e 100.")
        for _ in range(100 // VOLUME_STEP_PERCENT):
            self._media.control("volume_down")
        for _ in range(percent // VOLUME_STEP_PERCENT):
            self._media.control("volume_up")
        return f"Volume ajustado para {percent}%."

    def toggle_mute(self) -> str:
        self._media.control("mute")
        return "Alternei o mudo."

    def media(self, action: str) -> str:
        self._media.control(action)
        messages = {
            "play_pause": "Pronto, alternei entre tocar e pausar.",
            "next": "Próxima faixa.",
            "previous": "Faixa anterior.",
            "stop": "Reprodução parada.",
        }
        return messages.get(action, "Comando de mídia enviado.")

    # ------------------------------------------------------------------ brilho
    def get_brightness(self) -> int | None:
        result = self._run(
            _powershell("(Get-CimInstance -Namespace root/WMI -ClassName WmiMonitorBrightness).CurrentBrightness")
        )
        match = re.search(r"\d+", result.stdout or "")
        return int(match.group()) if match else None

    def set_brightness(self, percent: int) -> str:
        percent = max(0, min(100, percent))
        result = self._run(
            _powershell(
                "(Get-CimInstance -Namespace root/WMI -ClassName WmiMonitorBrightnessMethods)"
                f" | Invoke-CimMethod -MethodName WmiSetBrightness -Arguments @{{Timeout=1;Brightness={percent}}}"
            )
        )
        if result.returncode != 0:
            raise RuntimeError("Não consegui ajustar o brilho. Monitores externos geralmente não aceitam esse controle.")
        return f"Brilho ajustado para {percent}%."

    def change_brightness(self, delta: int) -> str:
        current = self.get_brightness()
        if current is None:
            raise RuntimeError(
                "Esta tela não aceita controle de brilho pelo Windows. Diga 'abrir configurações rápidas' para ajustar."
            )
        return self.set_brightness(current + delta)

    # ------------------------------------------------------------------ energia e sessão
    def lock(self) -> str:
        if os.name != "nt":
            raise RuntimeError("Bloquear a tela só está disponível no Windows.")
        ctypes.windll.user32.LockWorkStation()
        return "Tela bloqueada."

    def sleep(self) -> str:
        self._run(["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"])
        return "Suspendendo o computador."

    def shutdown(self, minutes: int = 0) -> str:
        seconds = max(0, minutes) * 60
        self._run(["shutdown", "/s", "/t", str(seconds)])
        if minutes:
            return f"O computador vai desligar em {minutes} minuto(s). Diga 'cancelar desligamento' para desistir."
        return "Desligando o computador."

    def restart(self, minutes: int = 0) -> str:
        self._run(["shutdown", "/r", "/t", str(max(0, minutes) * 60)])
        return "Reiniciando o computador." if not minutes else f"Vou reiniciar em {minutes} minuto(s)."

    def cancel_shutdown(self) -> str:
        result = self._run(["shutdown", "/a"])
        if result.returncode != 0:
            return "Não havia desligamento agendado."
        return "Desligamento cancelado."

    # ------------------------------------------------------------------ janelas e teclado
    def shortcut(self, name: str) -> str:
        keys = SHORTCUTS.get(name)
        if not keys:
            raise ValueError(f"Não conheço o atalho '{name}'.")
        self._hotkey(*keys)
        return "Feito."

    def press_key(self, spoken: str, times: int = 1) -> str:
        key = KEY_NAMES.get(spoken, spoken if len(spoken) == 1 else None)
        if key is None:
            raise ValueError(f"Não sei qual tecla é '{spoken}'.")
        for _ in range(max(1, min(times, 50))):
            self._hotkey(key)
        return f"Pressionei {spoken}."

    def type_text(self, text: str) -> str:
        if not text.strip():
            raise ValueError("Diga o que devo digitar.")
        if len(text) > 5000:
            raise ValueError("Texto longo demais para digitar de uma vez.")
        self._typer(text)
        return "Digitei."

    def scroll(self, direction: str) -> str:
        import pyautogui

        pyautogui.scroll(-600 if direction == "baixo" else 600)
        return "Rolei a página."

    def screenshot(self) -> str:
        import pyautogui

        self.screenshot_dir.mkdir(parents=True, exist_ok=True)
        path = self.screenshot_dir / f"print_{datetime.now():%Y-%m-%d_%H-%M-%S}.png"
        pyautogui.screenshot(str(path))
        return f"Print salvo em {path}."

    # ------------------------------------------------------------------ aplicativos
    def close_app(self, name: str) -> str:
        spoken = name.strip().lower()
        candidates = APP_ALIASES.get(spoken) or [spoken if spoken.endswith(".exe") else f"{spoken}.exe"]
        closed = []
        for image in candidates:
            # sem /F: o Windows pede para o app fechar e ele pode oferecer "salvar alterações"
            result = self._run(["taskkill", "/IM", image, "/T"])
            if result.returncode == 0:
                closed.append(image)
        if not closed:
            return f"Não encontrei '{name}' aberto."
        return f"Pedi para fechar {name}."

    def top_processes(self, limit: int = 5) -> str:
        import psutil

        usage: dict[str, int] = {}
        for process in psutil.process_iter(["name", "memory_info"]):
            try:
                name = (process.info["name"] or "?").removesuffix(".exe")
                usage[name] = usage.get(name, 0) + process.info["memory_info"].rss
            except (psutil.Error, AttributeError, TypeError):
                continue
        ranking = sorted(usage.items(), key=lambda item: item[1], reverse=True)[:limit]
        top = ", ".join(f"{name} ({rss / 1024**2:.0f} MB)" for name, rss in ranking)
        return f"Os programas que mais usam memória agora: {top}."

    # ------------------------------------------------------------------ informações
    def battery(self) -> str:
        import psutil

        info = psutil.sensors_battery()
        if info is None:
            return "Não encontrei bateria neste computador."
        status = "carregando" if info.power_plugged else "na bateria"
        text = f"Bateria em {info.percent:.0f}%, {status}."
        if not info.power_plugged and info.secsleft not in (psutil.POWER_TIME_UNKNOWN, psutil.POWER_TIME_UNLIMITED):
            hours, rest = divmod(int(info.secsleft), 3600)
            text += f" Restam cerca de {hours}h{rest // 60:02d}."
        return text

    def system_status(self) -> str:
        import psutil

        cpu = psutil.cpu_percent(interval=0.5)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage(os.path.splitdrive(str(Path.home()))[0] + os.sep if os.name == "nt" else "/")
        parts = [
            f"CPU em {cpu:.0f}%",
            f"memória em {memory.percent:.0f}% ({memory.used / 1024**3:.1f} de {memory.total / 1024**3:.1f} GB)",
            f"disco com {disk.free / 1024**3:.0f} GB livres",
        ]
        battery = psutil.sensors_battery()
        if battery is not None:
            parts.append(f"bateria em {battery.percent:.0f}%")
        return "Status: " + ", ".join(parts) + "."

    def disk_space(self) -> str:
        import psutil

        parts = []
        for partition in psutil.disk_partitions():
            try:
                usage = psutil.disk_usage(partition.mountpoint)
            except (PermissionError, OSError):
                continue
            if usage.total == 0:
                continue
            parts.append(f"{partition.device} {usage.free / 1024**3:.0f} GB livres de {usage.total / 1024**3:.0f} GB")
        return "Discos: " + "; ".join(parts) + "." if parts else "Não consegui ler os discos."

    def network(self) -> str:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
                probe.connect(("8.8.8.8", 80))
                local_ip = probe.getsockname()[0]
            online = True
        except OSError:
            local_ip, online = None, False
        ssid = None
        if os.name == "nt":
            result = self._run(["netsh", "wlan", "show", "interfaces"])
            match = re.search(r"^\s*SSID\s*:\s*(.+)$", result.stdout or "", re.MULTILINE)
            ssid = match.group(1).strip() if match else None
        if not online:
            return "Parece que você está sem internet."
        wifi = f" no Wi-Fi {ssid}" if ssid else ""
        return f"Conectado à internet{wifi}. IP local {local_ip}."

    def computer_info(self) -> str:
        return f"{platform.node()} com {platform.system()} {platform.release()}, processador {platform.processor() or platform.machine()}."

    # ------------------------------------------------------------------ preferências
    def set_dark_mode(self, enabled: bool) -> str:
        value = "0" if enabled else "1"
        key = r"HKCU\Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
        for name in ("AppsUseLightTheme", "SystemUsesLightTheme"):
            result = self._run(["reg", "add", key, "/v", name, "/t", "REG_DWORD", "/d", value, "/f"])
            if result.returncode != 0:
                raise RuntimeError("Não consegui alterar o tema do Windows.")
        return "Modo escuro ativado." if enabled else "Modo claro ativado."

    # ------------------------------------------------------------------ área de transferência
    @staticmethod
    def read_clipboard_static() -> str | None:
        try:
            import win32clipboard

            win32clipboard.OpenClipboard()
            try:
                if win32clipboard.IsClipboardFormatAvailable(win32clipboard.CF_UNICODETEXT):
                    return win32clipboard.GetClipboardData(win32clipboard.CF_UNICODETEXT)
                return None
            finally:
                win32clipboard.CloseClipboard()
        except Exception:
            return None

    @staticmethod
    def write_clipboard_static(text: str) -> None:
        import win32clipboard

        win32clipboard.OpenClipboard()
        try:
            win32clipboard.EmptyClipboard()
            win32clipboard.SetClipboardText(text, win32clipboard.CF_UNICODETEXT)
        finally:
            win32clipboard.CloseClipboard()

    def read_clipboard(self) -> str:
        text = self.read_clipboard_static()
        if not text:
            return "A área de transferência está vazia ou não contém texto."
        return f"Na área de transferência: {text[:1000]}"

    # ------------------------------------------------------------------ arquivos e terminal
    def create_folder(self, name: str, location: str | None = None) -> str:
        if not name or re.search(r'[<>:"/\\|?*]', name):
            raise ValueError("Nome de pasta inválido.")
        base = _known_folder(location)
        target = (base / name).resolve()
        if not target.is_relative_to(base.resolve()):
            raise ValueError("A pasta precisa ficar dentro do local escolhido.")
        target.mkdir(parents=True, exist_ok=True)
        return f"Pasta criada em {target}."

    def run_command(self, command: str) -> str:
        if not command.strip():
            raise ValueError("Diga o comando que devo executar.")
        result = self._run(_powershell(command))
        output = (result.stdout or "") + (result.stderr or "")
        output = output.strip()[:MAX_COMMAND_OUTPUT] or "(sem saída)"
        status = "concluído" if result.returncode == 0 else f"terminou com código {result.returncode}"
        return f"Comando {status}:\n{output}"


def _known_folder(location: str | None) -> Path:
    home = Path.home()
    spoken = (location or "area de trabalho").strip().lower()
    folders = {
        "area de trabalho": home / "Desktop",
        "desktop": home / "Desktop",
        "documentos": home / "Documents",
        "downloads": home / "Downloads",
        "imagens": home / "Pictures",
        "musicas": home / "Music",
        "videos": home / "Videos",
    }
    folder = folders.get(spoken)
    if folder is None:
        raise ValueError("Posso criar pastas na área de trabalho, documentos, downloads, imagens, músicas ou vídeos.")
    if spoken in ("area de trabalho", "desktop") and not folder.exists():
        onedrive = home / "OneDrive" / "Desktop"
        if onedrive.exists():
            return onedrive
    return folder
