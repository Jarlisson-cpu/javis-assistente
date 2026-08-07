from security.manager import PermissionManager


def test_permission_manager_defaults():
    pm = PermissionManager({"automation.open_app": False})
    assert pm.is_allowed("automation.open_app") is False
    # unspecified permission defaults to allow
    assert pm.is_allowed("some.unknown") is True
