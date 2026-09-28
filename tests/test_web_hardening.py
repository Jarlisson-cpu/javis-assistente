import http.client
import json
import threading
from types import SimpleNamespace

import pytest

from core.exceptions import ConfirmationDenied
from web.server import (
    JarvisWebHandler,
    JarvisWebServer,
    MAX_REQUEST_BYTES,
    _parse_history_limit,
    _safe_static_path,
    _validate_web_exposure,
    _validate_message_text,
    _validate_permission_updates,
)


class FakePermissionManager:
    def __init__(self):
        self.values = {"file.delete": True, "search.web": True}

    def is_allowed(self, key):
        return self.values.get(key, True)

    def set_permission(self, key, value):
        self.values[key] = value

    def list_permissions(self):
        return dict(self.values)


@pytest.fixture
def web_server():
    cleared = []

    class DenyConfirmation:
        async def confirm(self, action):
            raise ConfirmationDenied(action.key)

    core = SimpleNamespace(
        permission_manager=FakePermissionManager(),
        confirmation=DenyConfirmation(),
        memory=SimpleNamespace(clear_messages=lambda: cleared.append(True)),
        plugin_loader=SimpleNamespace(loaded={}),
        config=SimpleNamespace(app=SimpleNamespace(name="JARVIS", version="0.1.0")),
    )
    server = JarvisWebServer(("127.0.0.1", 0), JarvisWebHandler, core)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server, cleared
    server.shutdown()
    server.server_close()
    thread.join(timeout=2)


def _request(server, method, path, body=None, headers=None, include_headers=False):
    connection = http.client.HTTPConnection(*server.server_address, timeout=2)
    payload = json.dumps(body) if body is not None else None
    connection.request(method, path, body=payload, headers=headers or {})
    response = connection.getresponse()
    response_body = response.read()
    result = (response.status, response_body, dict(response.getheaders())) if include_headers else (response.status, response_body)
    connection.close()
    return result


def test_history_limit_is_bounded_and_rejects_invalid_values():
    assert _parse_history_limit("12") == 12
    assert _parse_history_limit("9000") == 500
    assert _parse_history_limit("0") == 1
    with pytest.raises(ValueError):
        _parse_history_limit("not-a-number")


def test_non_loopback_web_binding_requires_tls():
    _validate_web_exposure("127.0.0.1", tls_enabled=False, api_token=None)
    with pytest.raises(RuntimeError, match="TLS é obrigatório"):
        _validate_web_exposure("0.0.0.0", tls_enabled=False, api_token="a" * 40)
    with pytest.raises(RuntimeError, match="JARVIS_WEB_TOKEN"):
        _validate_web_exposure("0.0.0.0", tls_enabled=True, api_token=None)
    with pytest.raises(RuntimeError, match="32 caracteres"):
        _validate_web_exposure("127.0.0.1", tls_enabled=False, api_token="curto")
    with pytest.raises(RuntimeError, match="32 caracteres"):
        _validate_web_exposure("0.0.0.0", tls_enabled=True, api_token=" " * 40)
    _validate_web_exposure("0.0.0.0", tls_enabled=True, api_token="a" * 40)


def test_permission_updates_reject_unknown_keys_and_non_boolean_values():
    assert _validate_permission_updates({"search.web": False}) == {"search.web": False}
    with pytest.raises(ValueError):
        _validate_permission_updates({"admin.root": True})
    with pytest.raises(ValueError):
        _validate_permission_updates({"search.web": "false"})


def test_message_validation_rejects_empty_non_text_and_oversized_values():
    assert _validate_message_text("  olá  ") == "olá"
    for invalid in (None, "  ", "x" * 10001):
        with pytest.raises(ValueError):
            _validate_message_text(invalid)


def test_static_path_cannot_escape_public_directory(tmp_path, monkeypatch):
    import web.server as server_module

    public_dir = tmp_path / "public"
    public_dir.mkdir()
    (public_dir / "index.html").write_text("public", encoding="utf-8")
    private_file = tmp_path / "secret.txt"
    private_file.write_text("secret", encoding="utf-8")
    monkeypatch.setattr(server_module, "STATIC_DIR", public_dir)

    assert _safe_static_path("/static/index.html") == public_dir / "index.html"
    assert _safe_static_path("/static/../secret.txt") is None
    assert _safe_static_path("/static/../../secret.txt") is None


def test_http_api_rejects_oversized_payload_and_invalid_permissions(web_server):
    server, _ = web_server
    connection = http.client.HTTPConnection(*server.server_address, timeout=2)
    connection.putrequest("POST", "/api/message")
    connection.putheader("Content-Type", "application/json")
    connection.putheader("Content-Length", str(MAX_REQUEST_BYTES + 1))
    connection.endheaders()
    response = connection.getresponse()
    status = response.status
    response.read()
    connection.close()
    assert status == 413

    status, _ = _request(
        server,
        "POST",
        "/api/permissions",
        {"permissions": {"search.web": "false"}},
    )
    assert status == 400


def test_http_history_clear_cannot_bypass_confirmation(web_server):
    server, cleared = web_server

    status, body = _request(server, "POST", "/api/history/clear", {})

    assert status == 403
    assert b"cancelada" in body.lower()
    assert cleared == []


def test_http_api_requires_bearer_token_when_configured(web_server):
    server, _ = web_server
    server.api_token = "a" * 40

    status, _, headers = _request(server, "GET", "/api/status", include_headers=True)
    assert status == 401
    assert headers["WWW-Authenticate"] == "Bearer"
    assert headers["X-Content-Type-Options"] == "nosniff"

    status, _ = _request(
        server,
        "GET",
        "/api/status",
        headers={"Authorization": f"Bearer {'a' * 40}"},
    )
    assert status == 200

    server.api_token = "b" * 40
    status, _ = _request(
        server,
        "POST",
        "/api/permissions",
        {"permissions": {"search.web": False}},
    )
    assert status == 401
    assert server.core.permission_manager.is_allowed("search.web") is True