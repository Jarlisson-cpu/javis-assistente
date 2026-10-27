"""Ponto de entrada do JARVIS.

Uso:
    python main.py                         conversa por texto no terminal
    python main.py --voice                 controle total por voz ("Jarvis, ...")
    python main.py --gui                   interface gráfica (Tkinter)
    python main.py --web                   painel web em http://127.0.0.1:8000

Usuários:
    python main.py --criar-usuario joao --admin
    python main.py --usuarios
    python main.py --trocar-senha joao
    python main.py --remover-usuario joao
    python main.py --voice --usuario joao  usa o perfil "joao" nesta sessão
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import logging
import sys

from core.app import JarvisCore
from core.event_bus import Event
from users import UserError
from voice.assistant import VoiceAssistant, VoiceConfirmationProvider, extract_command


def _configure_console() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass


def _print_reply(event: Event) -> None:
    print(f"jarvis> {(event.payload or {}).get('text', '')}")


async def _repl(core: JarvisCore) -> None:
    """Loop de conversa por texto no terminal."""
    core.event_bus.subscribe("system_message", _print_reply)
    who = f", {core.current_user.display_name}" if core.current_user else ""
    print(f"\n{core.config.app.name} online{who}. Digite 'ajuda' para exemplos ou 'sair' para encerrar.\n")

    while True:
        try:
            text = await asyncio.to_thread(input, "você> ")
        except EOFError:
            break
        if text.strip().lower() in ("sair", "exit", "quit"):
            break
        if not text.strip():
            continue

        await core.event_bus.publish(Event(name="user_message", payload={"text": text}, source="terminal"))


def _extract_voice_command(transcript: str, wake_word: str) -> str | None:
    return extract_command(transcript, wake_word)


def _voice_startup_error(core: JarvisCore) -> str | None:
    if core.voice is None:
        return "Módulo de voz indisponível."
    if not core.permission_manager.is_allowed("voice.stt"):
        return "Reconhecimento de voz bloqueado pela política de permissões (voice.stt)."
    return core.voice.stt_unavailable_reason()


async def _voice_loop(core: JarvisCore) -> None:
    error = _voice_startup_error(core)
    if error:
        print(error)
        return

    core.event_bus.subscribe("system_message", _print_reply)
    core.confirmation.set_provider(VoiceConfirmationProvider(core.voice))
    if core.current_user:
        core.voice.speak(f"Olá, {core.current_user.display_name}. Estou ouvindo.")
    else:
        core.voice.speak("Jarvis online. Estou ouvindo.")
    await VoiceAssistant(core).run()


# ---------------------------------------------------------------------- usuários
def _ask_new_password() -> str:
    while True:
        password = getpass.getpass("Senha (mín. 6 caracteres): ")
        if password == getpass.getpass("Repita a senha: "):
            return password
        print("As senhas não conferem. Tente de novo.")


def _manage_users(core: JarvisCore, args: argparse.Namespace) -> bool:
    """Executa comandos de usuário; retorna True se algum foi executado."""
    try:
        if args.criar_usuario:
            display = input(f"Como o JARVIS deve te chamar? [{args.criar_usuario}]: ").strip() or args.criar_usuario
            first = core.users.count() == 0
            role = "admin" if args.admin or first else "user"
            user = core.users.create_user(args.criar_usuario, _ask_new_password(), display, role)
            extra = " (primeiro usuário: virou administrador)" if first and not args.admin else ""
            print(f"Usuário '{user.username}' criado como {user.role}{extra}.")
            return True
        if args.usuarios:
            users = core.users.list()
            if not users:
                print("Nenhum usuário. Crie um com: python main.py --criar-usuario seu_nome")
            for user in users:
                print(f"- {user.username:20} {user.display_name:25} {user.role:6} criado em {user.created_at:%d/%m/%Y}")
            return True
        if args.trocar_senha:
            core.users.set_password(args.trocar_senha, _ask_new_password())
            print("Senha alterada.")
            return True
        if args.remover_usuario:
            if input(f"Remover o usuário '{args.remover_usuario}'? [s/N]: ").strip().lower() not in ("s", "sim"):
                print("Cancelado.")
            elif core.users.delete(args.remover_usuario):
                print("Usuário removido.")
            else:
                print("Usuário não encontrado.")
            return True
    except UserError as exc:
        print(f"Erro: {exc}")
        return True
    return False


def _select_local_user(core: JarvisCore, username: str | None) -> bool:
    """Define o usuário ativo do terminal/voz/GUI. Retorna False se o login falhar."""
    if username is None:
        user = core.default_local_user()
        if user is None:
            return True
        username = user.username
    if core.users.get(username) is None:
        print(f"Usuário '{username}' não existe. Crie com: python main.py --criar-usuario {username}")
        return False
    password = None
    if core.config.users.require_password_locally:
        password = getpass.getpass(f"Senha de {username}: ")
    try:
        core.login(username, password)
    except UserError as exc:
        print(exc)
        return False
    return True


def main() -> None:
    _configure_console()
    parser = argparse.ArgumentParser(description="JARVIS — assistente pessoal com controle por voz")
    parser.add_argument("--gui", action="store_true", help="Abrir interface gráfica (Tkinter)")
    parser.add_argument("--web", action="store_true", help="Abrir interface web no navegador")
    parser.add_argument("--voice", "--voz", action="store_true", help="Controle total por voz")
    parser.add_argument("--host", default="127.0.0.1", help="Host para o servidor web")
    parser.add_argument("--port", type=int, default=8000, help="Porta para o servidor web")
    parser.add_argument("--usuario", help="Usuário ativo nesta sessão (terminal, voz ou GUI)")
    parser.add_argument("--criar-usuario", metavar="LOGIN", help="Cria um usuário (pede nome e senha)")
    parser.add_argument("--admin", action="store_true", help="Com --criar-usuario: cria como administrador")
    parser.add_argument("--usuarios", action="store_true", help="Lista os usuários")
    parser.add_argument("--trocar-senha", metavar="LOGIN", help="Troca a senha de um usuário")
    parser.add_argument("--remover-usuario", metavar="LOGIN", help="Remove um usuário")
    args = parser.parse_args()

    if args.gui:
        try:
            from gui.tk_app import run_gui

            run_gui(username=args.usuario)
            return
        except Exception as exc:  # pragma: no cover - runtime UI errors
            logging.getLogger("jarvis").exception("Falha ao iniciar GUI: %s", exc)
            print("Falha ao iniciar GUI, caindo para o terminal.")

    if args.web:
        try:
            from web.server import run_web

            run_web(host=args.host, port=args.port)
            return
        except Exception as exc:  # pragma: no cover - runtime web errors
            logging.getLogger("jarvis").exception("Falha ao iniciar servidor web: %s", exc)
            print(f"Falha ao iniciar interface web ({exc}), caindo para o terminal.")

    core = JarvisCore()
    if _manage_users(core, args):
        return
    if not _select_local_user(core, args.usuario):
        return
    core.bootstrap()
    try:
        if args.voice:
            asyncio.run(_voice_loop(core))
        else:
            asyncio.run(_repl(core))
    except KeyboardInterrupt:
        print("\nAté logo.")
    finally:
        core.shutdown()


if __name__ == "__main__":
    main()
