from types import SimpleNamespace

import pytest

from automation.automation import Automation


class DenyPermissionManager:
    def is_allowed(self, key: str) -> bool:
        return False


def test_click_is_blocked_when_permission_is_denied(monkeypatch):
    import automation.automation as automation_module

    called = False

    def fake_click(x, y):
        nonlocal called
        called = True

    monkeypatch.setattr(automation_module.pyautogui, "click", fake_click)
    automation = Automation(SimpleNamespace(permission_manager=DenyPermissionManager()))

    with pytest.raises(PermissionError, match="automation.click"):
        automation.click(10, 20)

    assert called is False