"""Fase 2 — memória de curto prazo e memória vetorial de longo prazo."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

from core.logger import get_logger

from memory.sqlite_store import MessageRecord, SQLiteStore
from memory.vector_store import ChromaStore, CHROMADB_AVAILABLE

logger = get_logger("memory")


class MemoryManager:
    """Gerencia memória de curto prazo (SQLite) e de longo prazo (ChromaDB)."""

    def __init__(
        self,
        db_path: str | Path = "jarvis_memory.db",
        vector_enabled: bool = False,
        vector_path: str | Path = "database/vectors",
        vector_collection: str = "jarvis_memory",
        embedding_model: str = "all-MiniLM-L6-v2",
    ) -> None:
        self.short_term = SQLiteStore(db_path)
        self.vector_enabled = vector_enabled and CHROMADB_AVAILABLE
        self.vector_memory: ChromaStore | None = None

        if vector_enabled:
            if self.vector_enabled:
                self.vector_memory = ChromaStore(
                    persist_directory=vector_path,
                    collection_name=vector_collection,
                    embedding_model=embedding_model,
                )
            else:
                logger.warning(
                    "Memória vetorial configurada, mas ChromaDB não está instalado. "
                    "Instale `chromadb` e `sentence-transformers` para habilitar."
                )

    def add_message(self, source: str, text: str) -> MessageRecord:
        record = self.short_term.add_message(source, text)
        if self.vector_memory is not None and text:
            try:
                self.vector_memory.add_document(
                    id=str(record.id),
                    text=text,
                    metadata={
                        "source": source,
                        "timestamp": record.timestamp.isoformat(),
                    },
                )
            except Exception:
                logger.exception("Falha ao indexar mensagem em ChromaDB")
        return record

    def list_messages(self, limit: int = 100) -> Iterable[MessageRecord]:
        return self.short_term.list_messages(limit=limit)

    def clear_messages(self) -> None:
        self.short_term.clear_messages()
        if self.vector_memory is not None:
            try:
                self.vector_memory.clear()
            except Exception:
                logger.exception("Falha ao limpar memória vetorial ChromaDB")

    def query_similar(self, query_text: str, limit: int = 5) -> list[dict[str, object]]:
        if self.vector_memory is None:
            return []
        try:
            return self.vector_memory.query(query_text, limit=limit)
        except Exception:
            logger.exception("Falha ao consultar memória vetorial ChromaDB")
            return []
