"""veyra-mcp — MCP-сервер Veyra.

Детекторы расхождений, противоречий и невыполненных обещаний в
стратегических документах коммерческого блока Avito.

ЭТАП: Фаза 1, Трек B — skeleton. Все инструменты возвращают заглушки.
Реальная логика заливается в Фазе 2, Трек E, и ТОЛЬКО после прохождения
гейта детекторов (Принцип 1 ТЗ v1.3). До этого момента сервис не
регистрируется в production mcp-registry — только staging/alpha.
"""
from __future__ import annotations

from fastapi import Depends, FastAPI

from app import tools
from app.auth import require_auth
from app.models import (
    CheckInitiativeRequest,
    FindContradictionsRequest,
    GetDocumentRequest,
    HealthResponse,
    SearchCorpusRequest,
    StubResponse,
)

app = FastAPI(
    title="veyra-mcp",
    description="Детекторы расхождений в стратегических документах. "
    "Skeleton-фаза: эндпоинты возвращают заглушки.",
    version="0.1.0-alpha",
)


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Единственный неглушёный эндпоинт на Фазе 1."""
    return HealthResponse()


@app.post(
    "/tools/check_initiative",
    response_model=StubResponse,
    dependencies=[Depends(require_auth)],
)
async def check_initiative(req: CheckInitiativeRequest) -> StubResponse:
    return await tools.check_initiative(req.text)


@app.post(
    "/tools/find_contradictions",
    response_model=StubResponse,
    dependencies=[Depends(require_auth)],
)
async def find_contradictions(req: FindContradictionsRequest) -> StubResponse:
    return await tools.find_contradictions(req.doc_id)


@app.post(
    "/tools/search_corpus",
    response_model=StubResponse,
    dependencies=[Depends(require_auth)],
)
async def search_corpus(req: SearchCorpusRequest) -> StubResponse:
    return await tools.search_corpus(req.query, req.top_k)


@app.post(
    "/tools/get_document",
    response_model=StubResponse,
    dependencies=[Depends(require_auth)],
)
async def get_document(req: GetDocumentRequest) -> StubResponse:
    return await tools.get_document(req.doc_id)
