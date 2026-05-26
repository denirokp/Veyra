"""ChromaDB wrapper — коллекции по статусу документа."""
from __future__ import annotations

from typing import Any

import chromadb
from chromadb import Collection

from app.settings import settings

_client: chromadb.ClientAPI | None = None


def get_client() -> chromadb.ClientAPI:
    global _client
    if _client is None:
        # anonymized_telemetry=False гасит шумные "Failed to send telemetry
        # event" — баг несовместимости Chroma с версией posthog, к работе
        # хранилища отношения не имеет.
        _client = chromadb.PersistentClient(
            path=settings.CHROMA_PERSIST_DIR,
            settings=chromadb.Settings(anonymized_telemetry=False),
        )
    return _client


def get_collection(name: str = "actual", workspace: str = "default") -> Collection:
    """
    Коллекции: 'actual', 'archive'. superseded не индексируется.
    Мультитенантность (PoC): имя коллекции включает workspace —
    `khronika_<workspace>_<name>`. Разные workspace = изолированные корпуса
    в одном Chroma. Дефолт `default` — обратная совместимость поведения.
    """
    return get_client().get_or_create_collection(
        name=f"khronika_{workspace}_{name}",
        metadata={"hnsw:space": "cosine"},
    )


def upsert_chunks(
    chunks: list[dict[str, Any]],
    collection_name: str = "actual",
    workspace: str = "default",
) -> None:
    col = get_collection(collection_name, workspace)
    # Chroma не принимает None в metadata — выкидываем
    metadatas = [
        {k: v for k, v in c["metadata"].items() if v is not None}
        for c in chunks
    ]
    col.upsert(
        ids=[c["id"] for c in chunks],
        embeddings=[c["embedding"] for c in chunks],
        documents=[c["content"] for c in chunks],
        metadatas=metadatas,
    )


def query_chunks(
    embedding: list[float],
    collection_name: str = "actual",
    n_results: int = 20,
    where: dict | None = None,
    workspace: str = "default",
) -> list[dict[str, Any]]:
    col = get_collection(collection_name, workspace)
    result = col.query(
        query_embeddings=[embedding],
        n_results=n_results,
        where=where,
        include=["documents", "metadatas", "distances"],
    )
    items = []
    for i, doc_id in enumerate(result["ids"][0]):
        items.append({
            "id": doc_id,
            "content": result["documents"][0][i],
            "metadata": result["metadatas"][0][i],
            "distance": result["distances"][0][i],
        })
    return items


def delete_document_chunks(
    document_id: str, collection_name: str = "actual", workspace: str = "default"
) -> None:
    col = get_collection(collection_name, workspace)
    col.delete(where={"document_id": document_id})


def drop_workspace(workspace: str) -> None:
    """Удаляет обе коллекции workspace — для чистого реиндекса именно его,
    не трогая другие корпуса."""
    client = get_client()
    for name in ("actual", "archive"):
        try:
            client.delete_collection(name=f"khronika_{workspace}_{name}")
        except Exception:
            pass  # коллекции может не быть — это нормально


def get_document_chunks(
    document_id: str, collection_name: str = "actual", workspace: str = "default"
) -> list[dict[str, Any]]:
    """Вернёт все чанки документа с embeddings — для миграции между коллекциями
    без пересчёта эмбеддингов."""
    col = get_collection(collection_name, workspace)
    result = col.get(
        where={"document_id": document_id},
        include=["documents", "metadatas", "embeddings"],
    )
    items: list[dict[str, Any]] = []
    for i, chunk_id in enumerate(result.get("ids", []) or []):
        items.append({
            "id": chunk_id,
            "content": (result.get("documents") or [None])[i],
            "metadata": (result.get("metadatas") or [{}])[i] or {},
            "embedding": (result.get("embeddings") or [None])[i],
        })
    return items
