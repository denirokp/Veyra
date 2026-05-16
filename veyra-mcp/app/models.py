"""Request/response-схемы veyra-mcp.

На этапе skeleton (Фаза 1, Трек B) ответы — заглушки. Схемы заданы сразу
по финальному контракту, чтобы при заливке реальной логики (Фаза 2,
Трек E) менялись только тела функций, а интерфейс оставался прежним.
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class CheckInitiativeRequest(BaseModel):
    text: str = Field(..., description="Текст инициативы для сверки с корпусом")


class FindContradictionsRequest(BaseModel):
    doc_id: str = Field(..., description="ID документа из корпуса")


class SearchCorpusRequest(BaseModel):
    query: str = Field(..., description="Поисковый запрос по корпусу")
    top_k: int = Field(5, ge=1, le=50, description="Сколько документов вернуть")


class GetDocumentRequest(BaseModel):
    doc_id: str = Field(..., description="ID документа из корпуса")


class StubResponse(BaseModel):
    """Унифицированный ответ-заглушка. Реальная логика — Фаза 2, Трек E."""

    status: str = "not_implemented"
    stub: bool = True
    tool: str
    echo: dict = Field(
        default_factory=dict,
        description="Эхо входа — чтобы при тесте видеть, что маршрутизация верна",
    )


class HealthResponse(BaseModel):
    status: str = "ok"
    service: str = "veyra-mcp"
    phase: str = "1 — skeleton (все инструменты возвращают заглушки)"
