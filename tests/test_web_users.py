import http.client
import json
import threading
from types import SimpleNamespace

import pytest

from skills import SkillRegistry
from users import SessionManager, UserStore
from web.confirmation import WebConfirmationProvider
from web.server import JarvisWebHandler, JarvisWebServer


class PermissionManager:
    def __init__(self):
        self.values = {}

    def is_allowed(self, key):
        return self.values.get(key, True)

    def set_permission(self, key, value):
        self.values[key] = value


@pytest.fixture
def server(tmp_path):
    users = UserStore(tmp_path / "db.sqlite")
    users.create_user("admin", "senha123", "Chefe", role="admin")
    users.create_user("convidado", "senha123")
    published = []
    core = SimpleNamespace(
        users=users,
        sessions=SessionManager(),
        permission_manager=PermissionManager(),
        skills=SkillRegistry(),
        event_bus=SimpleNamespace(publish_sync=published.append),
        plugin_loader=SimpleNamespace(loaded={}),
        config=SimpleNamespace(
            app=SimpleNamespace(name="JARVIS", version="1.0.0"),
            users=SimpleNamespace(web_login_required=True),
        ),
    )
    httpd = JarvisWebServer(("127.0.0.1", 0), JarvisWebHandler, core)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield httpd, published
    httpd.shutdown()
    httpd.server_close()
    thread.join(timeout=2)


def call(server, method, path, body=None, token=None):
    connection = http.client.HTTPConnection(*server.server_address, timeout=5)
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    connection.request(method, path, body=json.dumps(body) if body is not None else None, headers=headers)
    response = connection.getresponse()
    data = json.loads(response.read() or b"{}")
    connection.close()
    return response.status, data


def login(server, username):
    status, data = call(server, "POST", "/api/login", {"username": username, "password": "senha123"})
    assert status == 200
    return data["token"]


def test_api_requires_login_when_users_exist(server):
    httpd, _ = server
    status, data = call(httpd, "GET", "/api/status")
    assert status == 401
    assert data["login"] == "user"

    status, data = call(httpd, "GET", "/api/auth")
    assert status == 200 and data["login_required"] is True

    status, _ = call(httpd, "POST", "/api/login", {"username": "admin", "password": "errada"})
    assert status == 401


def test_logged_user_sends_messages_with_username(server):
    httpd, published = server
    token = login(httpd, "admin")

    status, data = call(httpd, "GET", "/api/status", token=token)
    assert status == 200 and data["user"]["display_name"] == "Chefe"

    status, _ = call(httpd, "POST", "/api/message", {"text": "que horas são"}, token=token)
    assert status == 200
    assert published[0].payload == {"text": "que horas são", "username": "admin"}

    call(httpd, "POST", "/api/logout", {}, token=token)
    status, _ = call(httpd, "GET", "/api/status", token=token)
    assert status == 401


def test_only_admin_changes_permissions(server):
    httpd, _ = server
    guest = login(httpd, "convidado")
    status, _ = call(httpd, "POST", "/api/permissions", {"permissions": {"search.web": False}}, token=guest)
    assert status == 403

    admin = login(httpd, "admin")
    status, _ = call(httpd, "POST", "/api/permissions", {"permissions": {"search.web": False}}, token=admin)
    assert status == 200
    assert httpd.core.permission_manager.is_allowed("search.web") is False


def test_login_is_rate_limited(server):
    httpd, _ = server
    statuses = [call(httpd, "POST", "/api/login", {"username": "admin", "password": "x"})[0] for _ in range(9)]
    assert statuses[-1] == 429


@pytest.mark.asyncio
async def test_web_confirmation_round_trip():
    import asyncio

    from core.confirmation import DestructiveAction

    provider = WebConfirmationProvider(timeout_seconds=5)
    task = asyncio.create_task(provider.ask(DestructiveAction(key="system.shutdown", description="Desligar")))
    await asyncio.sleep(0.05)
    pending = provider.list_pending()
    assert pending[0]["description"] == "Desligar"
    assert provider.answer(pending[0]["id"], True)
    assert await task is True
    assert provider.list_pending() == []
