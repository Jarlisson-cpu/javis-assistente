import pytest

from users import SessionManager, UserError, UserStore
from users.store import hash_password, verify_password


def test_password_hash_is_salted_and_verifiable():
    first, second = hash_password("segredo1"), hash_password("segredo1")
    assert first != second
    assert first.startswith("pbkdf2_sha256$")
    assert "segredo1" not in first
    assert verify_password("segredo1", first)
    assert not verify_password("errada", first)


def test_create_authenticate_and_manage_users(tmp_path):
    store = UserStore(tmp_path / "db.sqlite")
    user = store.create_user("Joao", "senha123", "João Silva", role="admin")

    assert user.username == "joao"
    assert user.display_name == "João Silva"
    assert user.is_admin
    assert store.authenticate("JOAO", "senha123").username == "joao"
    assert store.authenticate("joao", "errada") is None
    assert store.authenticate("ninguem", "senha123") is None

    store.set_password("joao", "nova-senha")
    assert store.authenticate("joao", "nova-senha") is not None
    assert store.set_display_name("joao", "Chefe").display_name == "Chefe"
    assert store.update_preferences("joao", tema="escuro").preferences == {"tema": "escuro"}
    assert [u.username for u in store.list()] == ["joao"]
    assert store.delete("joao") and store.count() == 0


def test_user_validation(tmp_path):
    store = UserStore(tmp_path / "db.sqlite")
    store.create_user("maria", "senha123")
    with pytest.raises(UserError, match="já existe"):
        store.create_user("maria", "outra123")
    with pytest.raises(UserError, match="6 caracteres"):
        store.create_user("pedro", "123")
    with pytest.raises(UserError, match="nome de usuário"):
        store.create_user("a b", "senha123")
    with pytest.raises(UserError, match="Papel"):
        store.create_user("ana", "senha123", role="root")


def test_sessions_expire_and_can_be_revoked():
    sessions = SessionManager(ttl_hours=1)
    token = sessions.create("joao")
    assert sessions.resolve(token) == "joao"
    sessions.revoke(token)
    assert sessions.resolve(token) is None

    expired = SessionManager(ttl_hours=-1)
    assert expired.resolve(expired.create("joao")) is None
    assert sessions.resolve(None) is None
