from core.event_bus import Event, EventBus
from plugins.search_web import SearchWebPlugin


def test_web_search_is_blocked_when_permission_is_denied(monkeypatch):
    import security.manager as security_manager
    import plugins.search_web as search_module

    class DenyPermissionManager:
        def is_allowed(self, key):
            return False

    opened = []
    monkeypatch.setattr(security_manager, "manager", DenyPermissionManager())
    monkeypatch.setattr(search_module.webbrowser, "open_new_tab", lambda url: opened.append(url))
    event_bus = EventBus()
    plugin = SearchWebPlugin()
    plugin.setup(event_bus)
    messages = []
    event_bus.subscribe("system_message", lambda event: messages.append(event.payload["text"]))

    plugin._on_user_message(
        Event(name="user_message", payload={"text": "buscar informação privada"}, source="voice")
    )

    assert opened == []
    assert any("bloqueada" in message.lower() for message in messages)