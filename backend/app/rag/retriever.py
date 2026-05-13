"""Hybrid retrieval — vector + BM25 + RRF fusion + hierarchy weighting."""
from __future__ import annotations

from dataclasses import dataclass, field

from rank_bm25 import BM25Okapi

from app.clients import embed_one
from app.storage import vector_db


@dataclass
class RetrievedChunk:
    id: str
    content: str
    metadata: dict
    score: float = 0.0

    @property
    def document_id(self) -> str:
        return self.metadata.get("document_id", "")

    @property
    def hierarchy_level(self) -> int:
        return int(self.metadata.get("hierarchy_level", 5))

    @property
    def status(self) -> str:
        return self.metadata.get("status", "unknown")

    @property
    def section(self) -> str:
        return self.metadata.get("section", "")

    @property
    def title(self) -> str:
        return self.metadata.get("title", "")


def _reciprocal_rank_fusion(
    *ranked_lists: list[RetrievedChunk], k: int = 60
) -> list[RetrievedChunk]:
    scores: dict[str, float] = {}
    chunks: dict[str, RetrievedChunk] = {}

    for ranked in ranked_lists:
        for rank, chunk in enumerate(ranked):
            scores[chunk.id] = scores.get(chunk.id, 0.0) + 1.0 / (k + rank + 1)
            chunks[chunk.id] = chunk

    for chunk_id in chunks:
        chunks[chunk_id].score = scores[chunk_id]

    return sorted(chunks.values(), key=lambda c: c.score, reverse=True)


def _apply_hierarchy_boost(chunks: list[RetrievedChunk]) -> list[RetrievedChunk]:
    """L1 документы получают буст, L5-L6 — штраф."""
    BOOST = {1: 1.5, 2: 1.2, 3: 1.0, 4: 1.0, 5: 0.7, 6: 0.5}
    for c in chunks:
        boost = BOOST.get(c.hierarchy_level, 0.8)
        c.score *= boost
    return sorted(chunks, key=lambda c: c.score, reverse=True)


def _dedupe_overlapping(chunks: list[RetrievedChunk]) -> list[RetrievedChunk]:
    """Чанки рядом по индексу + один документ часто имеют overlap (50 токенов
    окно). После RAG это даёт «два соседних чанка с почти одинаковым текстом»
    в топе и LLM получает дубль контекста. Убираем дубли по пересечению
    префикса 200 символов внутри одного документа."""
    kept: list[RetrievedChunk] = []
    seen_prefixes: dict[str, list[str]] = {}
    for c in chunks:
        doc_id = c.document_id or c.id
        prefix = (c.content or "")[:200].strip().lower()
        if not prefix:
            kept.append(c)
            continue
        previous = seen_prefixes.setdefault(doc_id, [])
        if any(prefix in p or p in prefix for p in previous):
            continue  # дубль с уже добавленным чанком из того же документа
        previous.append(prefix)
        kept.append(c)
    return kept


def _bm25_search(
    query: str,
    candidates: list[RetrievedChunk],
    top_k: int = 20,
) -> list[RetrievedChunk]:
    if not candidates:
        return []
    tokenized = [c.content.lower().split() for c in candidates]
    bm25 = BM25Okapi(tokenized)
    scores = bm25.get_scores(query.lower().split())
    ranked = sorted(
        zip(scores, candidates),
        key=lambda x: x[0],
        reverse=True,
    )
    result = []
    for score, chunk in ranked[:top_k]:
        chunk.score = score
        result.append(chunk)
    return result


async def retrieve(
    query: str,
    top_k: int = 10,
    include_archive: bool = False,
    segment_filter: str | None = None,
) -> list[RetrievedChunk]:
    """
    Основной hybrid retrieval:
    1. Векторный поиск (actual коллекция, опционально archive)
    2. BM25 по кандидатам
    3. RRF fusion
    4. Hierarchy boost
    5. top_k
    """
    query_embedding = await embed_one(query)

    where_filter = {}
    if segment_filter:
        where_filter["segment"] = segment_filter

    # Векторный поиск
    vec_results = vector_db.query_chunks(
        query_embedding,
        collection_name="actual",
        n_results=20,
        where=where_filter or None,
    )
    vec_chunks = [
        RetrievedChunk(id=r["id"], content=r["content"], metadata=r["metadata"])
        for r in vec_results
    ]

    if include_archive:
        arch_results = vector_db.query_chunks(
            query_embedding,
            collection_name="archive",
            n_results=10,
            where=where_filter or None,
        )
        arc_chunks = [
            RetrievedChunk(id=r["id"], content=r["content"], metadata=r["metadata"])
            for r in arch_results
        ]
        # Помечаем архивные
        for c in arc_chunks:
            c.metadata.setdefault("status", "archived")
        vec_chunks.extend(arc_chunks)

    if not vec_chunks:
        return []

    # BM25 по тем же кандидатам
    bm25_chunks = _bm25_search(query, list(vec_chunks), top_k=20)

    # RRF fusion
    fused = _reciprocal_rank_fusion(vec_chunks, bm25_chunks)

    # Hierarchy boost
    boosted = _apply_hierarchy_boost(fused)

    # Дедуп overlapping чанков (соседи по индексу часто пересекаются)
    deduped = _dedupe_overlapping(boosted)

    return deduped[:top_k]


async def retrieve_for_writing(
    topic: str,
    top_k: int = 8,
) -> list[RetrievedChunk]:
    """Для написания документов — только actual, без архива."""
    chunks = await retrieve(topic, top_k=top_k, include_archive=False)
    return [c for c in chunks if c.status == "actual"]
