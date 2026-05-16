"""Инструменты veyra-mcp.

Skeleton-фаза: каждая функция возвращает заглушку. Реальная логика
(retrieval + детекторы) заливается в Фазе 2, Трек E — ТОЛЬКО после
прохождения гейта детекторов (Принцип 1 ТЗ v1.3).

До прохождения гейта эти функции НЕ должны вызывать LLM и НЕ должны
обращаться к индексу корпуса.
"""
from __future__ import annotations

from app.models import StubResponse


def _stub(tool: str, echo: dict) -> StubResponse:
    return StubResponse(tool=tool, echo=echo)


async def check_initiative(text: str) -> StubResponse:
    """Сверка инициативы с корпусом → список расхождений с цитатами. Трек E."""
    return _stub("check_initiative", {"text_len": len(text)})


async def find_contradictions(doc_id: str) -> StubResponse:
    """Расхождения для документа из корпуса. Трек E."""
    return _stub("find_contradictions", {"doc_id": doc_id})


async def search_corpus(query: str, top_k: int) -> StubResponse:
    """Чистый retrieval по корпусу. Трек E."""
    return _stub("search_corpus", {"query": query, "top_k": top_k})


async def get_document(doc_id: str) -> StubResponse:
    """Полный текст документа — для просмотра цитат. Трек E."""
    return _stub("get_document", {"doc_id": doc_id})
