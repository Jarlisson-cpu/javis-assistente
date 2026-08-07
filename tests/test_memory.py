from pathlib import Path

from memory import CHROMADB_AVAILABLE, MemoryManager


def test_add_and_list(tmp_path: Path) -> None:
    db = tmp_path / "mem.db"
    store = MemoryManager(db_path=db)

    rec = store.add_message("tester", "hello world")
    assert rec.id is not None

    msgs = list(store.list_messages(limit=10))
    assert any(m.text == "hello world" for m in msgs)


def test_vector_memory_optional(tmp_path: Path) -> None:
    if not CHROMADB_AVAILABLE:
        return

    db = tmp_path / "mem.db"
    store = MemoryManager(db_path=db, vector_enabled=True, vector_path=tmp_path / "vectors")

    rec = store.add_message("tester", "vector hello world")
    assert rec.id is not None

    results = store.query_similar("hello world", limit=1)
    assert isinstance(results, list)
    assert all("id" in item and "document" in item for item in results)
