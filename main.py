"""Ponto de entrada do JARVIS (Fase 0/1 — núcleo apenas, sem voz/GUI ainda).

Uso:
    python main.py
"""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
import logging
import re
import sys
from pathlib import Path

from core.app import JarvisCore
from core.event_bus import Event


async def _repl(core: JarvisCore) -> None:
    """Loop de conversa por texto no terminal."""
    core.event_bus.subscribe(
        "system_message",
        lambda event: print(f"jarvis> {(event.payload or {}).get('text', '')}"),
    )
    print(f"\n{core.config.app.name} online. Digite 'sair' para encerrar.\n")

    while True:
        text = await asyncio.to_thread(input, "você> ")
        if text.strip().lower() in ("sair", "exit", "quit"):
            break

        await core.event_bus.publish(
            Event(name="user_message", payload={"text": text}, source="terminal")
        )


def _extract_voice_command(transcript: str, wake_word: str) -> str | None:
    if not wake_word.strip():
        return transcript.strip()

    match = re.search(rf"\b{re.escape(wake_word.strip())}\b", transcript, re.IGNORECASE)
    if not match:
        return None
    return (transcript[: match.start()] + transcript[match.end() :]).strip(" \t,.:;!?-")


async def _voice_loop(core: JarvisCore) -> None:
    error = _voice_startup_error(core)
    if error:
        print(error)
        return

    core.config.voice.enable_stt = True
    wake_word = core.config.voice.wake_word
    core.event_bus.subscribe(
        "system_message",
        lambda event: print(f"jarvis> {(event.payload or {}).get('text', '')}"),
    )
    print(
        f"\nVoz ativa. Diga '{wake_word}' antes do comando; diga 'sair' para encerrar.\n"
    )

    while True:
        command = await _capture_voice_command(core, wake_word)
        if not command:
            continue
        if command.lower() in ("sair", "encerrar", "parar"):
            break

        await core.event_bus.publish(
            Event(name="user_message", payload={"text": command}, source="voice")
        )


def _voice_startup_error(core: JarvisCore) -> str | None:
    if core.voice is None:
        return "Módulo de voz indisponível."
    if not core.permission_manager or not core.permission_manager.is_allowed("voice.stt"):
        return "Reconhecimento de voz bloqueado pela política de permissões."

    model_path = Path(core.config.voice.stt_model_path)
    missing_modules = []
    for module in ("vosk", "sounddevice"):
        try:
            if importlib.util.find_spec(module) is None:
                missing_modules.append(module)
        except (ImportError, ValueError):
            missing_modules.append(module)
    if missing_modules or not model_path.is_dir():
        missing = ", ".join(missing_modules) or "nenhuma biblioteca"
        return f"STT indisponível. Instale: {missing}; coloque um modelo Vosk em {model_path}."
    return None


async def _capture_voice_command(core: JarvisCore, wake_word: str) -> str | None:
    transcript = await asyncio.to_thread(core.voice.listen, 5)
    if not transcript:
        return None

    command = _extract_voice_command(transcript, wake_word)
    if command is None:
        return None
    if command:
        return command

    print("Ouvindo comando...")
    follow_up = await asyncio.to_thread(core.voice.listen, 8)
    return follow_up.strip() if follow_up else None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gui", action="store_true", help="Abrir interface gráfica (Tkinter)")
    parser.add_argument("--web", action="store_true", help="Abrir interface web no navegador")
    parser.add_argument("--voice", action="store_true", help="Ativar conversa por voz (Vosk)")
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
    if args.voice:
        try:
            asyncio.run(_voice_loop(core))
        except KeyboardInterrupt:
            print("\nModo de voz encerrado.")
        return
    asyncio.run(_repl(core))


if __name__ == "__main__":
    main()
