from __future__ import annotations

import json
import logging
import asyncio
import hmac
import os
import ssl
import threading
import time
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from core.app import JarvisCore
from core.confirmation import DestructiveAction
from core.exceptions import ConfirmationDenied
from core.event_bus import Event
from security.permissions import registry as permission_registry
from users import context as user_context
from web.confirmation import WebConfirmationProvider

logger = logging.getLogger("jarvis.web")

PUBLIC_API_PATHS = {"/api/login", "/api/auth"}
MAX_LOGIN_ATTEMPTS = 8
LOGIN_WINDOW_SECONDS = 300

STATIC_DIR = Path(__file__).resolve().parent / "static"
MAX_REQUEST_BYTES = 64 * 1024
MAX_MESSAGE_LENGTH = 10_000
MAX_HISTORY_LIMIT = 500
UNKNOWN_ENDPOINT_MESSAGE = "Endpoint não encontrado"


def _validate_web_exposure(host: str, tls_enabled: bool, api_token: str | None) -> None:
    loopback_hosts = {"127.0.0.1", "localhost", "::1"}
    external = host not in loopback_hosts
    if external and not tls_enabled:
        raise RuntimeError("TLS é obrigatório ao expor o servidor web fora do loopback")
    if external and (not api_token or len(api_token.strip()) < 32):
        raise RuntimeError("JARVIS_WEB_TOKEN com ao menos 32 caracteres é obrigatório fora do loopback")
    if api_token and len(api_token.strip()) < 32:
        raise RuntimeError("JARVIS_WEB_TOKEN deve ter ao menos 32 caracteres")


def _has_valid_bearer_token(header: str | None, expected_token: str | None) -> bool:
    if expected_token is None:
        return True
    if not header or not header.startswith("Bearer "):
        return False
    supplied_token = header.removeprefix("Bearer ").strip()
    return hmac.compare_digest(supplied_token, expected_token)


def _parse_history_limit(raw_limit: str) -> int:
    try:
        limit = int(raw_limit)
    except (TypeError, ValueError) as exc:
        raise ValueError("limit deve ser um número inteiro") from exc
    return min(max(limit, 1), MAX_HISTORY_LIMIT)


def _validate_permission_updates(values: object) -> dict[str, bool]:
    if not isinstance(values, dict):
        raise ValueError("permissions deve ser um objeto")

    known_keys = {permission.key for permission in permission_registry.list()}
    updates: dict[str, bool] = {}
    for key, allowed in values.items():
        if key not in known_keys:
            raise ValueError(f"Permissão desconhecida: {key}")
        if not isinstance(allowed, bool):
            raise ValueError(f"O valor de {key} deve ser booleano")
        updates[key] = allowed
    return updates


def _validate_message_text(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("text deve ser uma string")
    text = value.strip()
    if not text:
        raise ValueError("Texto não pode ser vazio")
    if len(text) > MAX_MESSAGE_LENGTH:
        raise ValueError(f"Texto excede o limite de {MAX_MESSAGE_LENGTH} caracteres")
    return text


def _safe_static_path(path: str) -> Path | None:
    safe_path = path[len("/static/") :] if path.startswith("/static/") else path.lstrip("/")
    base = STATIC_DIR.resolve()
    target = (base / safe_path).resolve()
    if not target.is_relative_to(base) or not target.is_file():
        return None
    return target


def json_response(
    handler: SimpleHTTPRequestHandler,
    data: object,
    status: int = HTTPStatus.OK,
    extra_headers: dict[str, str] | None = None,
) -> None:
    payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(payload)))
    for name, value in (extra_headers or {}).items():
        handler.send_header(name, value)
    handler.end_headers()
    handler.wfile.write(payload)


class JarvisWebHandler(SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        logger.info(format, *args)

    def end_headers(self) -> None:
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "same-origin")
        super().end_headers()

    user = None

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path.startswith("/api/"):
            if not self._authorize_api_request(parsed.path):
                return
            return self.handle_api_get(parsed)

        if parsed.path == "/":
            self.serve_static("/index.html")
            return

        self.serve_static(parsed.path)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if not parsed.path.startswith("/api/"):
            self.send_error(HTTPStatus.NOT_FOUND, UNKNOWN_ENDPOINT_MESSAGE)
            return
        if not self._authorize_api_request(parsed.path):
            return

        try:
            content_length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            json_response(self, {"error": "Content-Length inválido"}, status=HTTPStatus.BAD_REQUEST)
            return
        if content_length < 0:
            json_response(self, {"error": "Content-Length inválido"}, status=HTTPStatus.BAD_REQUEST)
            return
        if content_length > MAX_REQUEST_BYTES:
            json_response(self, {"error": "Payload excede o limite permitido"}, status=HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
            return
        try:
            body = self.rfile.read(content_length).decode("utf-8")
        except UnicodeDecodeError:
            json_response(self, {"error": "JSON deve usar UTF-8"}, status=HTTPStatus.BAD_REQUEST)
            return
        try:
            payload = json.loads(body) if body else {}
        except json.JSONDecodeError:
            json_response(self, {"error": "JSON inválido"}, status=HTTPStatus.BAD_REQUEST)
            return
        if not isinstance(payload, dict):
            json_response(self, {"error": "Payload deve ser um objeto JSON"}, status=HTTPStatus.BAD_REQUEST)
            return

        if parsed.path == "/api/login":
            return self.handle_login(payload)
        if parsed.path == "/api/logout":
            return self.handle_logout()
        if parsed.path == "/api/message":
            return self.handle_send_message(payload)
        if parsed.path == "/api/permissions":
            return self.handle_update_permissions(payload)
        if parsed.path == "/api/history/clear":
            return self.handle_clear_history()
        if parsed.path == "/api/confirmations":
            return self.handle_answer_confirmation(payload)

        self.send_error(HTTPStatus.NOT_FOUND, UNKNOWN_ENDPOINT_MESSAGE)

    # ------------------------------------------------------------------ autenticação
    def _users_store(self):
        return getattr(self.server.core, "users", None)

    def _login_required(self) -> bool:
        users = self._users_store()
        config = getattr(self.server.core, "config", None)
        required = getattr(getattr(config, "users", None), "web_login_required", True)
        return bool(users is not None and required and users.count() > 0)

    def _bearer(self) -> str | None:
        header = self.headers.get("Authorization") or ""
        return header.removeprefix("Bearer ").strip() if header.startswith("Bearer ") else None

    def _authorize_api_request(self, path: str = "") -> bool:
        self.user = None
        sessions = getattr(self.server.core, "sessions", None)
        username = sessions.resolve(self._bearer()) if sessions is not None else None
        if username and self._users_store() is not None:
            self.user = self._users_store().get(username)

        if path in PUBLIC_API_PATHS:
            return True

        expected_token = getattr(self.server, "api_token", None)
        static_ok = expected_token is not None and _has_valid_bearer_token(
            self.headers.get("Authorization"), expected_token
        )
        if self.user is not None or static_ok:
            return True
        if expected_token is None and not self._login_required():
            return True

        json_response(
            self,
            {"error": "Autenticação necessária", "login": "user" if self._login_required() else "token"},
            status=HTTPStatus.UNAUTHORIZED,
            extra_headers={"WWW-Authenticate": "Bearer"},
        )
        return False

    def _require_admin(self) -> bool:
        """Com usuários cadastrados, só administradores mudam permissões ou apagam histórico."""
        if not self._login_required() or self.user is None or self.user.is_admin:
            return True
        json_response(self, {"error": "Apenas administradores podem fazer isso"}, status=HTTPStatus.FORBIDDEN)
        return False

    def handle_login(self, payload: dict[str, object]) -> None:
        users = self._users_store()
        sessions = getattr(self.server.core, "sessions", None)
        if users is None or sessions is None:
            json_response(self, {"error": "Login indisponível"}, status=HTTPStatus.NOT_FOUND)
            return
        if not self.server.allow_login_attempt(self.client_address[0]):
            json_response(self, {"error": "Muitas tentativas. Aguarde alguns minutos."}, status=HTTPStatus.TOO_MANY_REQUESTS)
            return
        username, password = payload.get("username"), payload.get("password")
        if not isinstance(username, str) or not isinstance(password, str):
            json_response(self, {"error": "Informe usuário e senha"}, status=HTTPStatus.BAD_REQUEST)
            return
        user = users.authenticate(username, password)
        if user is None:
            json_response(self, {"error": "Usuário ou senha inválidos"}, status=HTTPStatus.UNAUTHORIZED)
            return
        token = sessions.create(user.username)
        logger.info("Login web: %s", user.username)
        json_response(self, {"token": token, "user": user.to_public_dict()})

    def handle_logout(self) -> None:
        sessions = getattr(self.server.core, "sessions", None)
        if sessions is not None:
            sessions.revoke(self._bearer())
        json_response(self, {"ok": True})

    def handle_auth(self) -> None:
        json_response(
            self,
            {
                "login_required": self._login_required(),
                "token_required": getattr(self.server, "api_token", None) is not None,
                "user": self.user.to_public_dict() if self.user else None,
            },
        )

    def handle_api_get(self, parsed) -> None:
        if parsed.path == "/api/history":
            return self.handle_history(parsed)
        if parsed.path == "/api/permissions":
            return self.handle_permissions()
        if parsed.path == "/api/status":
            return self.handle_status()
        if parsed.path == "/api/auth":
            return self.handle_auth()
        if parsed.path == "/api/skills":
            return self.handle_skills()
        if parsed.path == "/api/confirmations":
            return self.handle_list_confirmations()

        self.send_error(HTTPStatus.NOT_FOUND, UNKNOWN_ENDPOINT_MESSAGE)

    def handle_skills(self) -> None:
        skills = getattr(self.server.core, "skills", None)
        items = [
            {"name": s.name, "description": s.description, "examples": s.examples, "category": s.category}
            for s in (skills.list() if skills is not None else [])
        ]
        json_response(self, {"skills": items})

    def _web_confirmation(self) -> WebConfirmationProvider | None:
        provider = getattr(self.server, "confirmation_provider", None)
        return provider if isinstance(provider, WebConfirmationProvider) else None

    def handle_list_confirmations(self) -> None:
        provider = self._web_confirmation()
        json_response(self, {"pending": provider.list_pending() if provider else []})

    def handle_answer_confirmation(self, payload: dict[str, object]) -> None:
        provider = self._web_confirmation()
        confirmation_id, approved = payload.get("id"), payload.get("approved")
        if provider is None or not isinstance(confirmation_id, str) or not isinstance(approved, bool):
            json_response(self, {"error": "Informe id e approved (booleano)"}, status=HTTPStatus.BAD_REQUEST)
            return
        if not provider.answer(confirmation_id, approved):
            json_response(self, {"error": "Confirmação não encontrada ou expirada"}, status=HTTPStatus.NOT_FOUND)
            return
        json_response(self, {"ok": True})

    def handle_history(self, parsed) -> None:
        query = parse_qs(parsed.query)
        try:
            limit = _parse_history_limit(query.get("limit", [200])[0])
        except ValueError as exc:
            json_response(self, {"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
            return
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
        manager = self.server.core.permission_manager
        perms = [
            {
                "key": perm.key,
                "description": perm.description,
                "allowed": bool(manager.is_allowed(perm.key)) if manager else perm.default,
            }
            for perm in permission_registry.list()
        ]
        json_response(self, {"permissions": perms, "can_edit": self.user is None or self.user.is_admin})

    def handle_update_permissions(self, payload: dict[str, object]) -> None:
        if not self._require_admin():
            return
        if not self.server.core.permission_manager:
            json_response(self, {"error": "Gerenciador de permissões indisponível"}, status=HTTPStatus.INTERNAL_SERVER_ERROR)
            return

        try:
            values = _validate_permission_updates(payload.get("permissions"))
        except ValueError as exc:
            json_response(self, {"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
            return

        for key, allowed in values.items():
            self.server.core.permission_manager.set_permission(key, bool(allowed))

        json_response(self, {"ok": True})

    def handle_send_message(self, payload: dict[str, object]) -> None:
        try:
            text = _validate_message_text(payload.get("text", ""))
        except ValueError as exc:
            json_response(self, {"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
            return

        payload_out: dict[str, object] = {"text": text}
        if self.user is not None:
            payload_out["username"] = self.user.username
            user_context.set_current_user(self.user)
        event = Event(name="user_message", payload=payload_out, source="web")
        self.server.core.event_bus.publish_sync(event)
        json_response(self, {"ok": True})

    def handle_clear_history(self) -> None:
        if not self._require_admin():
            return
        try:
            permission_manager = self.server.core.permission_manager
            if not permission_manager or not permission_manager.is_allowed("file.delete"):
                json_response(self, {"error": "Ação bloqueada pela permissão file.delete"}, status=HTTPStatus.FORBIDDEN)
                return
            asyncio.run(
                self.server.core.confirmation.confirm(
                    DestructiveAction(
                        key="file.delete",
                        description="Limpar todo o histórico de mensagens",
                    )
                )
            )
            self.server.core.memory.clear_messages()
            json_response(self, {"ok": True})
        except ConfirmationDenied:
            json_response(self, {"error": "Limpeza do histórico cancelada"}, status=HTTPStatus.FORBIDDEN)
        except Exception as exc:
            logger.exception("Falha ao limpar histórico")
            json_response(self, {"error": str(exc)}, status=HTTPStatus.INTERNAL_SERVER_ERROR)

    def handle_status(self) -> None:
        plugins = [
            {"name": plugin.name, "version": plugin.version, "description": getattr(plugin, "description", "")}
            for plugin in self.server.core.plugin_loader.loaded.values()
        ]
        ai_provider = None
        chat = self.server.core.plugin_loader.loaded.get("chat_ai")
        if chat is not None and hasattr(chat, "_ai_manager"):
            ai_provider = chat._ai_manager.provider_name
        json_response(
            self,
            {
                "app": {"name": self.server.core.config.app.name, "version": self.server.core.config.app.version},
                "plugins": plugins,
                "ai_provider": ai_provider,
                "user": self.user.to_public_dict() if self.user else None,
            },
        )

    def serve_static(self, path: str) -> None:
        target = _safe_static_path(path)
        if target is None:
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
    def __init__(
        self,
        server_address: tuple[str, int],
        RequestHandlerClass: type[JarvisWebHandler],
        core: JarvisCore,
        api_token: str | None = None,
    ) -> None:
        super().__init__(server_address, RequestHandlerClass)
        self.core = core
        self.api_token = api_token
        self.confirmation_provider: WebConfirmationProvider | None = None
        self._login_attempts: dict[str, list[float]] = {}
        self._login_lock = threading.Lock()

    def allow_login_attempt(self, client: str) -> bool:
        """Limita tentativas de login por IP para dificultar força bruta."""
        now = time.monotonic()
        with self._login_lock:
            recent = [t for t in self._login_attempts.get(client, []) if now - t < LOGIN_WINDOW_SECONDS]
            if len(recent) >= MAX_LOGIN_ATTEMPTS:
                self._login_attempts[client] = recent
                return False
            recent.append(now)
            self._login_attempts[client] = recent
            return True


def run_web(host: str = "127.0.0.1", port: int = 8000) -> None:
    core = JarvisCore()
    core.bootstrap()
    # o navegador fala as respostas; o servidor fica em silêncio para não duplicar a voz
    core.speak_responses = False
    confirmation_provider = WebConfirmationProvider(core.config.security.confirmation_timeout_seconds)
    core.confirmation.set_provider(confirmation_provider)
    certfile = os.getenv("JARVIS_TLS_CERTFILE") or None
    keyfile = os.getenv("JARVIS_TLS_KEYFILE") or None
    api_token = os.getenv("JARVIS_WEB_TOKEN") or None
    if bool(certfile) != bool(keyfile):
        raise RuntimeError("Configure JARVIS_TLS_CERTFILE e JARVIS_TLS_KEYFILE juntos")
    _validate_web_exposure(host, tls_enabled=bool(certfile and keyfile), api_token=api_token)
    server_address = (host, port)
    httpd = JarvisWebServer(server_address, JarvisWebHandler, core, api_token=api_token)
    httpd.confirmation_provider = confirmation_provider
    protocol = "http"
    if certfile and keyfile:
        tls_context = ssl.create_default_context(purpose=ssl.Purpose.CLIENT_AUTH)
        tls_context.load_cert_chain(certfile=certfile, keyfile=keyfile)
        httpd.socket = tls_context.wrap_socket(httpd.socket, server_side=True)
        protocol = "https"
    logger.info("Servidor web do Jarvis rodando em %s://%s:%d", protocol, host, port)
    print(f"JARVIS web em {protocol}://{host}:{port} — Ctrl+C para encerrar.")
    if core.users.count() == 0:
        print("Dica: crie um usuário com 'python main.py --criar-usuario seu_nome' para proteger o painel com login.")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        logger.info("Servidor web interrompido pelo usuário")
    finally:
        httpd.server_close()
