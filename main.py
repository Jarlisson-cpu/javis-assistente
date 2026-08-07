"""Ponto de entrada do JARVIS (Fase 0/1 — núcleo apenas, sem voz/GUI ainda).

Uso:
    python main.py
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys

from core.app import JarvisCore
from core.event_bus import Event


async def _repl(core: JarvisCore) -> None:
    """Loop de texto temporário, até as Fases 4 (voz) e 5 (GUI) chegarem."""
    print(f"\n{core.config.app.name} — núcleo online. Digite 'sair' para encerrar.\n")

    while True:
        text = await asyncio.to_thread(input, "você> ")
        if text.strip().lower() in ("sair", "exit", "quit"):
            break

        await core.event_bus.publish(Event(name="user_message", payload={"text": text}))
        print("jarvis> (ainda sem módulo de IA conectado — chega na Fase 3)")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gui", action="store_true", help="Abrir interface gráfica (Tkinter)")
    parser.add_argument("--web", action="store_true", help="Abrir interface web no navegador")
    parser.add_argument("--host", default="127.0.0.1", help="Host para o servidor web")
    parser.add_argument("--port", type=int, default=8000, help="Porta para o servidor web")
    args = parser.parse_args()

    if args.gui:
        try:
            # run GUI entrypoint
            from gui.tk_app import run_gui

            run_gui()
            return
        except Exception as exc:  # pragma: no cover - runtime UI errors
            logging.getLogger("jarvis").exception("Falha ao iniciar GUI: %s", exc)
            print("Falha ao iniciar GUI, caindo para REPL.")

    if args.web:
        try:
            from web.server import run_web

            run_web(host=args.host, port=args.port)
            return
        except Exception as exc:  # pragma: no cover - runtime web errors
            logging.getLogger("jarvis").exception("Falha ao iniciar servidor web: %s", exc)
            print("Falha ao iniciar interface web, caindo para REPL.")

    core = JarvisCore()
    core.bootstrap()
    asyncio.run(_repl(core))


if __name__ == "__main__":
    main()
