from pathlib import Path

from memory.sqlite_store import SQLiteStore


def test_add_and_list(tmp_path: Path) -> None:
    db = tmp_path / "mem.db"
    store = SQLiteStore(db_path=db)

    rec = store.add_message("tester", "hello world")
    assert rec.id is not None

    msgs = list(store.list_messages(limit=10))
    assert any(m.text == "hello world" for m in msgs)
