import asyncio
import logging
import threading
import tkinter as tk
from tkinter import scrolledtext, simpledialog, messagebox

from core.app import JarvisCore
from core.event_bus import Event
from core.logger import get_logger
from security.manager import manager as permission_manager
from security.permissions import registry as permission_registry


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


class GUIConfirmationProvider:
    async def ask(self, action) -> bool:
        # run in main thread
        loop = asyncio.get_event_loop()
        fut = loop.create_future()

        def ask_sync():
            result = messagebox.askyesno("Confirmar ação", action.description)
            loop.call_soon_threadsafe(fut.set_result, result)

        # execute in Tk mainloop via after
        try:
            root = tk._default_root
            if root:
                root.after(0, ask_sync)
            else:
                # fallback: blocking
                result = messagebox.askyesno("Confirmar ação", action.description)
                fut.set_result(result)
        except Exception:
            fut.set_result(False)

        return await fut


class JarvisGUI:
    def __init__(self, core: JarvisCore) -> None:
        self.core = core
        # switch confirmation provider to GUI
        try:
            self.core.confirmation._provider = GUIConfirmationProvider()
        except Exception:
            pass

        self.root = tk.Tk()
        self.root.title(f"{self.core.config.app.name} — GUI")
        self.root.geometry("800x500")

        paned = tk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True)

        # history panel
        left_frame = tk.Frame(paned)
        self.history_text = scrolledtext.ScrolledText(left_frame, state="disabled", width=40)
        self.history_text.pack(fill=tk.BOTH, expand=True)

        hist_btn_frame = tk.Frame(left_frame)
        hist_btn_frame.pack(fill=tk.X)
        refresh_btn = tk.Button(hist_btn_frame, text="Atualizar", command=self.load_history)
        refresh_btn.pack(side=tk.LEFT, padx=4, pady=4)
        clear_btn = tk.Button(hist_btn_frame, text="Limpar Histórico", command=self.clear_history)
        clear_btn.pack(side=tk.RIGHT, padx=4, pady=4)

        paned.add(left_frame)

        # logs panel
        right_frame = tk.Frame(paned)
        self.log_text = scrolledtext.ScrolledText(right_frame, state="disabled")
        self.log_text.pack(fill=tk.BOTH, expand=True)
        paned.add(right_frame)

        entry_frame = tk.Frame(self.root)
        entry_frame.pack(fill=tk.X)

        self.entry = tk.Entry(entry_frame)
        self.entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(4, 2), pady=4)
        self.entry.bind("<Return>", lambda e: self.send_message())

        send_btn = tk.Button(entry_frame, text="Enviar", command=self.send_message)
        send_btn.pack(side=tk.RIGHT, padx=(2, 4))

        # attach logging handler
        handler = TextHandler(self.log_text)
        handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)-8s | %(name)s | %(message)s", datefmt="%Y-%m-%d %H:%M:%S"))
        logging.getLogger("jarvis").addHandler(handler)

        # subscribe to new messages to refresh history
        try:
            self.core.event_bus.subscribe("user_message", lambda e: self.root.after(100, self.load_history))
            self.core.event_bus.subscribe("system_message", lambda e: self.root.after(100, self.load_history))
        except Exception:
            pass

        # initial load
        perm_btn = tk.Button(self.root, text="Permissões", command=self.open_permissions_window)
        perm_btn.pack(fill=tk.X, padx=4, pady=4)

        self.root.after(200, self.load_history)

    def send_message(self) -> None:
        text = self.entry.get().strip()
        if not text:
            return
        self.entry.delete(0, tk.END)
        # publish event synchronously
        self.core.event_bus.publish_sync(Event(name="user_message", payload={"text": text}, source="gui"))
        # also refresh history shortly after sending
        try:
            self.root.after(100, self.load_history)
        except Exception:
            pass

    def start(self) -> None:
        self.root.mainloop()

    def load_history(self, limit: int = 200) -> None:
        try:
            msgs = list(self.core.memory.list_messages(limit=limit))
            self.history_text.configure(state="normal")
            self.history_text.delete("1.0", tk.END)
            for m in msgs:
                self.history_text.insert(tk.END, f"[{m.timestamp.isoformat()}] {m.source}: {m.text}\n")
            self.history_text.configure(state="disabled")
        except Exception:
            logger = get_logger("gui.history")
            logger.exception("Falha ao carregar histórico")

    def clear_history(self) -> None:
        from core.confirmation import DestructiveAction

        def ask_and_clear() -> None:
            try:
                import asyncio

                action = DestructiveAction(
                    key="automation.delete_file",
                    description="Limpar todo o histórico de mensagens",
                )
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    loop.run_until_complete(self.core.confirmation.confirm(action))
                except Exception:
                    return
                self.core.memory.clear_messages()
                self.load_history()
            except Exception:
                pass

        threading.Thread(target=ask_and_clear, daemon=True).start()

    def open_permissions_window(self) -> None:
        if not permission_manager:
            messagebox.showinfo("Permissões", "O gerenciador de permissões não está disponível.")
            return

        win = tk.Toplevel(self.root)
        win.title("Gerenciar permissões")
        win.geometry("520x480")

        frame = tk.Frame(win)
        frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        vars_map: dict[str, tk.BooleanVar] = {}
        for perm in permission_registry.list():
            value = permission_manager.is_allowed(perm.key)
            var = tk.BooleanVar(value=value)
            chk = tk.Checkbutton(
                frame,
                text=f"{perm.key}: {perm.description}",
                variable=var,
                anchor="w",
                justify="left",
                wraplength=480,
            )
            chk.pack(fill=tk.X, pady=2)
            vars_map[perm.key] = var

        def save_permissions() -> None:
            for key, var in vars_map.items():
                permission_manager.set_permission(key, var.get())
            self._publish_system("Permissões atualizadas.")
            win.destroy()

        save_btn = tk.Button(win, text="Salvar", command=save_permissions)
        save_btn.pack(side=tk.BOTTOM, pady=10)

    def _publish_system(self, message: str) -> None:
        self.core.event_bus.publish_sync(Event(name="system_message", payload={"text": message}, source="jarvis"))


def run_gui():
    core = JarvisCore()
    core.bootstrap()
    gui = JarvisGUI(core)
    gui.start()


if __name__ == "__main__":
    run_gui()
