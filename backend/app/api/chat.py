"""API чата — два РАЗНЫХ эндпоинта, не путать.

  GET  /api/retrieve — ЦЕЛЕВОЙ ПУТЬ. Чистый retrieval, без LLM. Источник
                       данных для veyra-mcp: сервер отдаёт куски
                       документов, рассуждение делает Claude. Всегда
                       включён, это слой данных.

  POST /api/chat     — LEGACY. Серверный «мозг»: orchestrator + docs-agent
                       синтезируют ответ на сервере (LLM на живом пути).
                       Используется только React-админ-панелью, продуктовым
                       путём НЕ является. Гейтится флагом ENABLE_LEGACY_CHAT.
                       Продуктовый живой путь — Claude через veyra-mcp;
                       серверный мозг развивать не нужно.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents import orchestrator
from app.models.schemas import ChatRequest, ChatResponse
from app.settings import settings
from app.storage.sql_db import get_session

router = APIRouter(tags=["chat"])


@router.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    db: AsyncSession = Depends(get_session),
) -> ChatResponse:
    """LEGACY серверный мозг — только для React-админ-панели.

    Продуктовый живой путь — Claude через veyra-mcp, не этот эндпоинт.
    Отключается флагом ENABLE_LEGACY_CHAT=0 (см. settings.py).
    """
    if not settings.ENABLE_LEGACY_CHAT:
        raise HTTPException(
            status_code=404,
            detail=(
                "Серверный /api/chat отключён (ENABLE_LEGACY_CHAT=0). "
                "Живой путь — Claude через veyra-mcp."
            ),
        )
    return await orchestrator.run(request, db=db)


@router.get("/retrieve")
async def retrieve_passages(
    query: str,
    top_k: int = 10,
    include_archive: bool = False,
):
    """Чистый retrieval — релевантные фрагменты корпуса БЕЗ LLM-синтеза.

    Целевой путь: это сырьё для veyra-mcp — сервер отдаёт куски
    документов, а рассуждение (синтез ответа, написание, анализ) делает
    уже Claude. LLM здесь не вызывается — только локальные эмбеддинги +
    BM25. Не гейтится ENABLE_LEGACY_CHAT — это слой данных, не «мозг».
    """
    from app.rag.retriever import retrieve

    chunks = await retrieve(query, top_k=top_k, include_archive=include_archive)
    return [
        {
            "id": c.id,
            "content": c.content,
            "document_id": c.document_id,
            "title": c.title,
            "section": c.section,
            "status": c.status,
            "score": round(c.score, 4),
        }
        for c in chunks
    ]
