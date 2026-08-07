from __future__ import annotations

from pathlib import Path
from typing import Any

from core.logger import get_logger

try:
    import chromadb
    from chromadb.config import Settings
    from chromadb.utils import embedding_functions
    CHROMADB_AVAILABLE = True
except ImportError:  # pragma: no cover
    chromadb = None  # type: ignore[assignment]
    Settings = None  # type: ignore[assignment]
    embedding_functions = None  # type: ignore[assignment]
    CHROMADB_AVAILABLE = False

logger = get_logger("vector_store")


class ChromaStore:
    """Armazena e busca vetores de texto usando ChromaDB."""

    def __init__(
        self,
        persist_directory: str | Path = "database/vectors",
        collection_name: str = "jarvis_memory",
        embedding_model: str = "all-MiniLM-L6-v2",
    ) -> None:
        if not CHROMADB_AVAILABLE:
            raise ImportError(
                "ChromaDB não está instalado. Instale `chromadb` e `sentence-transformers` para usar a memória vetorial."
            )

        self.persist_directory = Path(persist_directory)
        self.persist_directory.mkdir(parents=True, exist_ok=True)

        settings = Settings(
            chroma_db_impl="duckdb+parquet",
            persist_directory=str(self.persist_directory),
        )
        self.client = chromadb.Client(settings)
        self.embedding_function = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name=embedding_model
        )
        self.collection = self.client.get_or_create_collection(
            name=collection_name,
            embedding_function=self.embedding_function,
        )

    def add_document(self, id: str, text: str, metadata: dict[str, Any] | None = None) -> None:
        if metadata is None:
            metadata = {}

        self.collection.add(
            ids=[id],
            documents=[text],
            metadatas=[metadata],
        )
        self.client.persist()
        logger.debug("Mensagem indexada em ChromaDB: %s", id)

    def query(self, query_text: str, limit: int = 5) -> list[dict[str, Any]]:
        results = self.collection.query(
            query_texts=[query_text],
            n_results=limit,
            include=["ids", "documents", "metadatas", "distances"],
        )

        rows: list[dict[str, Any]] = []
        ids = results.get("ids", [[]])[0]
        docs = results.get("documents", [[]])[0]
        metas = results.get("metadatas", [[]])[0]
        distances = results.get("distances", [[]])[0]

        for idx, document, metadata, distance in zip(ids, docs, metas, distances):
            rows.append(
                {
                    "id": idx,
                    "document": document,
                    "metadata": metadata,
                    "distance": distance,
                }
            )

        return rows

    def clear(self) -> None:
        self.collection.delete(where={})
        self.client.persist()
        logger.info("Memória vetorial ChromaDB limpa")
