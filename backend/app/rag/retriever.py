"""Hybrid retrieval — vector + BM25 + RRF fusion + reranking."""
from __future__ import annotations

from dataclasses import dataclass, field

from rank_bm25 import BM25Okapi

from app.storage import vector_db


@dataclass
class RetrievedChunk:
    id: str
    content: str
    metadata: dict
    score: float = 0.0


def _reciprocal_rank_fusion(
    *ranked_lists: list[RetrievedChunk], k: int = 60
) -> list[RetrievedChunk]:
    scores: dict[str, float] = {}
    chunks: dict[str, RetrievedChunk] = {}

    for ranked in ranked_lists:
        for rank, chunk in enumerate(ranked):
            scores[chunk.id] = scores.get(chunk.id, 0.0) + 1.0 / (k + rank + 1)
            chunks[chunk.id] = chunk

    for chunk_id, score in scores.items():
        chunks[chunk_id].score = score

    return sorted(chunks.values(), key=lambda c: c.score, reverse=True)


async def _get_query_embedding(query: str) -> list[float]:
    # TODO: OpenAI text-embedding-3-large
    raise NotImplementedError


def _bm25_search(
    query: str,
    candidate_chunks: list[RetrievedChunk],
    top_k: int = 20,
) -> list[RetrievedChunk]:
    tokenized = [c.content.lower().split() for c in candidate_chunks]
    bm25 = BM25Okapi(tokenized)
    scores = bm25.get_scores(query.lower().split())
    ranked = sorted(
        zip(scores, candidate_chunks),
        key=lambda x: x[0],
        reverse=True,
    )
    return [c for _, c in ranked[:top_k]]


async def retrieve(
    query: str,
    top_k: int = 10,
    include_archive: bool = False,
) -> list[RetrievedChunk]:
    embedding = await _get_query_embedding(query)

    # Векторный поиск
    vec_results = vector_db.query_chunks(embedding, collection_name="actual", n_results=20)
    vec_chunks = [
        RetrievedChunk(id=r["id"], content=r["content"], metadata=r["metadata"])
        for r in vec_results
    ]

    if include_archive:
        arch_results = vector_db.query_chunks(embedding, collection_name="archive", n_results=10)
        vec_chunks += [
            RetrievedChunk(id=r["id"], content=r["content"], metadata=r["metadata"])
            for r in arch_results
        ]

    # BM25
    bm25_chunks = _bm25_search(query, vec_chunks, top_k=20)

    # RRF fusion
    fused = _reciprocal_rank_fusion(vec_chunks, bm25_chunks)

    # TODO: cross-encoder reranking
    return fused[:top_k]
