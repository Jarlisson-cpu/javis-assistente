from __future__ import annotations

import json
import logging
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from core.app import JarvisCore
from core.event_bus import Event
from security.permissions import registry as permission_registry

logger = logging.getLogger("web")

STATIC_DIR = Path(__file__).resolve().parent / "static"


def json_response(handler: SimpleHTTPRequestHandler, data: object, status: int = HTTPStatus.OK) -> None:
    payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(payload)))
    handler.end_headers()
    handler.wfile.write(payload)


class JarvisWebHandler(SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        logger.info(format, *args)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path.startswith("/api/"):
            return self.handle_api_get(parsed)

        if parsed.path == "/":
            self.serve_static("/index.html")
            return

        self.serve_static(parsed.path)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if not parsed.path.startswith("/api/"):
            self.send_error(HTTPStatus.NOT_FOUND, "Endpoint não encontrado")
            return

        content_length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(content_length).decode("utf-8")
        try:
            payload = json.loads(body) if body else {}
        except json.JSONDecodeError:
            json_response(self, {"error": "JSON inválido"}, status=HTTPStatus.BAD_REQUEST)
            return

        if parsed.path == "/api/message":
            return self.handle_send_message(payload)
        if parsed.path == "/api/permissions":
            return self.handle_update_permissions(payload)
        if parsed.path == "/api/history/clear":
            return self.handle_clear_history()

        self.send_error(HTTPStatus.NOT_FOUND, "Endpoint não encontrado")

    def handle_api_get(self, parsed) -> None:
        if parsed.path == "/api/history":
            return self.handle_history(parsed)
        if parsed.path == "/api/permissions":
            return self.handle_permissions()
        if parsed.path == "/api/status":
            return self.handle_status()

        self.send_error(HTTPStatus.NOT_FOUND, "Endpoint não encontrado")

    def handle_history(self, parsed) -> None:
        query = parse_qs(parsed.query)
        limit = int(query.get("limit", [200])[0])
        messages = []
        for message in self.server.core.memory.list_messages(limit=limit):
            messages.append(
                {
                    "id": message.id,
                    "timestamp": message.timestamp.isoformat(),
                    "source": message.source,
                    "text": message.text,
                }
            )
        json_response(self, {"messages": messages})

    def handle_permissions(self) -> None:
        current = self.server.core.permission_manager.list_permissions() if self.server.core.permission_manager else {}
        perms = [
            {"key": perm.key, "description": perm.description, "allowed": bool(current.get(perm.key, True))}
            for perm in permission_registry.list()
        ]
        json_response(self, {"permissions": perms})

    def handle_update_permissions(self, payload: dict[str, object]) -> None:
        if not isinstance(payload, dict):
            json_response(self, {"error": "Payload inválido"}, status=HTTPStatus.BAD_REQUEST)
            return

        if not self.server.core.permission_manager:
            json_response(self, {"error": "Gerenciador de permissões indisponível"}, status=HTTPStatus.INTERNAL_SERVER_ERROR)
            return

        values = payload.get("permissions")
        if not isinstance(values, dict):
            json_response(self, {"error": "permissions deve ser um objeto"}, status=HTTPStatus.BAD_REQUEST)
            return

        for key, allowed in values.items():
            self.server.core.permission_manager.set_permission(key, bool(allowed))

        json_response(self, {"ok": True})

    def handle_send_message(self, payload: dict[str, object]) -> None:
        text = str(payload.get("text", "")).strip()
        if not text:
            json_response(self, {"error": "Texto não pode ser vazio"}, status=HTTPStatus.BAD_REQUEST)
            return

        event = Event(name="user_message", payload={"text": text}, source="web")
        self.server.core.event_bus.publish_sync(event)
        json_response(self, {"ok": True})

    def handle_clear_history(self) -> None:
        try:
            self.server.core.memory.clear_messages()
            json_response(self, {"ok": True})
        except Exception as exc:
            logger.exception("Falha ao limpar histórico")
            json_response(self, {"error": str(exc)}, status=HTTPStatus.INTERNAL_SERVER_ERROR)

    def handle_status(self) -> None:
        plugins = [
            {"name": plugin.name, "version": plugin.version, "description": getattr(plugin, "description", "")}
            for plugin in self.server.core.plugin_loader.loaded.values()
        ]
        json_response(self, {"app": {"name": self.server.core.config.app.name, "version": self.server.core.config.app.version}, "plugins": plugins})

    def serve_static(self, path: str) -> None:
        if path.startswith("/static/"):
            safe_path = path[len("/static/"):]
        else:
            safe_path = path.lstrip("/")
        target = STATIC_DIR / safe_path
        if not target.exists() or not target.is_file():
            self.send_error(HTTPStatus.NOT_FOUND, "Arquivo não encontrado")
            return

        content_type = self.guess_type(str(target))
        try:
            with target.open("rb") as f:
                data = f.read()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        except Exception:
            self.send_error(HTTPStatus.INTERNAL_SERVER_ERROR, "Falha ao servir arquivo")


class JarvisWebServer(ThreadingHTTPServer):
    def __init__(self, server_address: tuple[str, int], RequestHandlerClass: type[JarvisWebHandler], core: JarvisCore) -> None:
        super().__init__(server_address, RequestHandlerClass)
        self.core = core


def run_web(host: str = "127.0.0.1", port: int = 8000) -> None:
    core = JarvisCore()
    core.bootstrap()
    server_address = (host, port)
    httpd = JarvisWebServer(server_address, JarvisWebHandler, core)
    logger.info("Servidor web do Jarvis rodando em http://%s:%d", host, port)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        logger.info("Servidor web interrompido pelo usuário")
    finally:
        httpd.server_close()
