import asyncio
import logging
import threading
import tkinter as tk
from tkinter import messagebox, scrolledtext

from core.app import JarvisCore
from core.confirmation import ConfirmationProvider, DestructiveAction
from core.event_bus import Event
from core.logger import get_logger
from security.permissions import registry as permission_registry
from voice.assistant import VoiceAssistant

logger = get_logger("gui")

BG = "#0f172a"
PANEL = "#111c33"
TEXT = "#e5e7eb"
MUTED = "#94a3b8"
ACCENT = "#38bdf8"
USER_COLOR = "#7dd3fc"
JARVIS_COLOR = "#86efac"


class TextHandler(logging.Handler):
    def __init__(self, text_widget: scrolledtext.ScrolledText) -> None:
        super().__init__()
        self.text_widget = text_widget

    def emit(self, record: logging.LogRecord) -> None:
        msg = self.format(record)

        def append():
            self.text_widget.configure(state="normal")
            self.text_widget.insert(tk.END, msg + "\n")
            self.text_widget.configure(state="disabled")
            self.text_widget.yview(tk.END)

        try:
            self.text_widget.after(0, append)
        except Exception:
            pass


class GUIConfirmationProvider(ConfirmationProvider):
    """Mostra a pergunta numa caixa de diálogo, sempre na thread do Tk."""

    def __init__(self, root: tk.Tk) -> None:
        self._root = root

    async def ask(self, action: DestructiveAction) -> bool:
        answered = threading.Event()
        result = {"value": False}

        def ask_sync() -> None:
            result["value"] = messagebox.askyesno("Confirmar ação", action.description, parent=self._root)
            answered.set()

        self._root.after(0, ask_sync)
        await asyncio.to_thread(answered.wait)
        return result["value"]


class JarvisGUI:
    def __init__(self, core: JarvisCore) -> None:
        self.core = core
        self.root = tk.Tk()
        self.root.title(f"{self.core.config.app.name}")
        self.root.geometry("980x620")
        self.root.configure(bg=BG)
        self.core.confirmation.set_provider(GUIConfirmationProvider(self.root))
        self._listening = False
        self._voice_thread: threading.Thread | None = None

        header = tk.Frame(self.root, bg=BG)
        header.pack(fill=tk.X, padx=12, pady=(12, 6))
        tk.Label(header, text="JARVIS", fg=ACCENT, bg=BG, font=("Segoe UI", 20, "bold")).pack(side=tk.LEFT)
        user = self.core.current_user
        who = f"Olá, {user.display_name}" if user else "Sem usuário (crie com --criar-usuario)"
        self.status = tk.Label(header, text=who, fg=MUTED, bg=BG, font=("Segoe UI", 10))
        self.status.pack(side=tk.LEFT, padx=16)
        tk.Button(header, text="Permissões", command=self.open_permissions_window).pack(side=tk.RIGHT, padx=4)
        tk.Button(header, text="Limpar histórico", command=self.clear_history).pack(side=tk.RIGHT, padx=4)
        tk.Button(header, text="Comandos", command=self.show_commands).pack(side=tk.RIGHT, padx=4)

        paned = tk.PanedWindow(self.root, orient=tk.HORIZONTAL, bg=BG, sashwidth=6)
        paned.pack(fill=tk.BOTH, expand=True, padx=12)

        self.chat = scrolledtext.ScrolledText(
            paned, state="disabled", wrap=tk.WORD, bg=PANEL, fg=TEXT, font=("Segoe UI", 11), relief=tk.FLAT
        )
        self.chat.tag_configure("user", foreground=USER_COLOR, font=("Segoe UI", 11, "bold"))
        self.chat.tag_configure("jarvis", foreground=JARVIS_COLOR, font=("Segoe UI", 11, "bold"))
        self.chat.tag_configure("meta", foreground=MUTED, font=("Segoe UI", 8))
        paned.add(self.chat, width=640)

        self.log_text = scrolledtext.ScrolledText(
            paned, state="disabled", bg=BG, fg=MUTED, font=("Consolas", 8), relief=tk.FLAT
        )
        paned.add(self.log_text)

        entry_frame = tk.Frame(self.root, bg=BG)
        entry_frame.pack(fill=tk.X, padx=12, pady=12)
        self.mic_button = tk.Button(entry_frame, text="🎤 Ouvir", width=14, command=self.toggle_voice)
        self.mic_button.pack(side=tk.LEFT, padx=(0, 6))
        self.entry = tk.Entry(entry_frame, font=("Segoe UI", 12))
        self.entry.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=6)
        self.entry.bind("<Return>", lambda e: self.send_message())
        self.entry.focus_set()
        tk.Button(entry_frame, text="Enviar", width=10, command=self.send_message).pack(side=tk.RIGHT, padx=(6, 0))

        handler = TextHandler(self.log_text)
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s", datefmt="%H:%M:%S"))
        logging.getLogger("jarvis").addHandler(handler)

        self.core.event_bus.subscribe("user_message", lambda e: self.root.after(150, self.load_history))
        self.core.event_bus.subscribe("system_message", lambda e: self.root.after(150, self.load_history))
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.root.after(200, self.load_history)

    # ------------------------------------------------------------------ conversa
    def send_message(self) -> None:
        text = self.entry.get().strip()
        if not text:
            return
        self.entry.delete(0, tk.END)
        event = Event(name="user_message", payload={"text": text}, source="gui")
        threading.Thread(target=self.core.event_bus.publish_sync, args=(event,), daemon=True).start()

    def load_history(self, limit: int = 200) -> None:
        try:
            username = self.core.current_user.username if self.core.current_user else None
            messages = list(self.core.memory.list_messages(limit=limit, username=username))
            self.chat.configure(state="normal")
            self.chat.delete("1.0", tk.END)
            for message in reversed(messages):
                is_jarvis = message.source == "jarvis"
                self.chat.insert(tk.END, "JARVIS  " if is_jarvis else "Você  ", "jarvis" if is_jarvis else "user")
                local_time = message.timestamp.astimezone().strftime("%d/%m %H:%M")
                self.chat.insert(tk.END, f"{local_time} · {message.source}\n", "meta")
                self.chat.insert(tk.END, f"{message.text}\n\n")
            self.chat.configure(state="disabled")
            self.chat.yview(tk.END)
        except Exception:
            logger.exception("Falha ao carregar histórico")

    # ------------------------------------------------------------------ voz
    def toggle_voice(self) -> None:
        if self.core.voice is None:
            messagebox.showinfo("Voz", "Módulo de voz indisponível.")
            return
        reason = self.core.voice.stt_unavailable_reason()
        if reason:
            messagebox.showinfo("Voz", reason)
            return
        if self._listening:
            self._listening = False
            self.mic_button.configure(text="🎤 Ouvir")
            self.status.configure(text="Microfone desligado")
            return
        self._listening = True
        self.mic_button.configure(text="⏹ Parar")
        self.status.configure(text=f"Ouvindo... diga '{self.core.config.voice.wake_word}' e o pedido")
        self._voice_thread = threading.Thread(target=self._voice_worker, daemon=True)
        self._voice_thread.start()

    def _voice_worker(self) -> None:
        assistant = VoiceAssistant(self.core, output=lambda text: None)

        async def loop() -> None:
            self.core.config.voice.enable_stt = True
            while self._listening:
                command = await assistant.next_command()
                if command and self._listening and not await assistant.handle(command):
                    self._listening = False

        asyncio.run(loop())
        self.root.after(0, lambda: self.mic_button.configure(text="🎤 Ouvir"))

    # ------------------------------------------------------------------ ações
    def show_commands(self) -> None:
        win = tk.Toplevel(self.root)
        win.title("O que o JARVIS sabe fazer")
        win.geometry("640x520")
        text = scrolledtext.ScrolledText(win, wrap=tk.WORD, font=("Segoe UI", 10))
        text.pack(fill=tk.BOTH, expand=True)
        by_category: dict[str, list[str]] = {}
        for skill in self.core.skills.list():
            examples = ", ".join(f"“{e}”" for e in skill.examples[:2])
            by_category.setdefault(skill.category, []).append(f"• {skill.description}  {examples}")
        for category, lines in by_category.items():
            text.insert(tk.END, f"{category.upper()}\n" + "\n".join(lines) + "\n\n")
        text.insert(
            tk.END,
            "TAMBÉM\n• abrir <app, site ou pasta> • buscar/pesquisar <termo> • buscar música/vídeo <termo>\n"
            "• ler site <url> • ler imagem <arquivo> • rascunho email <para> | <assunto> | <texto>\n"
            "• planejar / revisar / explicar <assunto>\n• Com uma chave de IA no .env, qualquer pedido em linguagem livre.",
        )
        text.configure(state="disabled")

    def clear_history(self) -> None:
        def ask_and_clear() -> None:
            try:
                asyncio.run(
                    self.core.confirmation.confirm(
                        DestructiveAction(key="file.delete", description="Limpar todo o histórico de mensagens")
                    )
                )
            except Exception:
                return
            self.core.memory.clear_messages()
            self.root.after(0, self.load_history)

        threading.Thread(target=ask_and_clear, daemon=True).start()

    def open_permissions_window(self) -> None:
        permission_manager = self.core.permission_manager
        user = self.core.current_user
        if user is not None and not user.is_admin:
            messagebox.showinfo("Permissões", "Apenas administradores podem alterar permissões.")
            return

        win = tk.Toplevel(self.root)
        win.title("Gerenciar permissões")
        win.geometry("560x600")

        canvas = tk.Canvas(win)
        frame = tk.Frame(canvas)
        scrollbar = tk.Scrollbar(win, command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        canvas.create_window((0, 0), window=frame, anchor="nw")
        frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))

        vars_map: dict[str, tk.BooleanVar] = {}
        for perm in permission_registry.list():
            var = tk.BooleanVar(value=permission_manager.is_allowed(perm.key))
            tk.Checkbutton(
                frame, text=f"{perm.key}: {perm.description}", variable=var, anchor="w", justify="left", wraplength=480
            ).pack(fill=tk.X, pady=2)
            vars_map[perm.key] = var

        def save_permissions() -> None:
            for key, var in vars_map.items():
                if permission_manager.is_allowed(key) != var.get():
                    permission_manager.set_permission(key, var.get())
            self._publish_system("Permissões atualizadas.")
            win.destroy()

        tk.Button(win, text="Salvar", command=save_permissions).pack(side=tk.BOTTOM, pady=10)

    def _publish_system(self, message: str) -> None:
        self.core.event_bus.publish_sync(Event(name="system_message", payload={"text": message}, source="jarvis"))

    def start(self) -> None:
        self.root.mainloop()

    def close(self) -> None:
        self._listening = False
        self.core.shutdown()
        self.root.destroy()


def run_gui(username: str | None = None) -> None:
    core = JarvisCore()
    user = core.users.get(username) if username else core.default_local_user()
    if username and user is None:
        raise SystemExit(f"Usuário '{username}' não existe. Crie com: python main.py --criar-usuario {username}")
    if user is not None:
        core.login(user.username)
    core.bootstrap()
    gui = JarvisGUI(core)
    gui.start()


if __name__ == "__main__":
    run_gui()
