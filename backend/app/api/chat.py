from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents import orchestrator
from app.models.schemas import ChatRequest, ChatResponse
from app.storage.sql_db import get_session

router = APIRouter(tags=["chat"])


@router.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    db: AsyncSession = Depends(get_session),
) -> ChatResponse:
    return await orchestrator.run(request, db=db)


@router.get("/retrieve")
async def retrieve_passages(
    query: str,
    top_k: int = 10,
    include_archive: bool = False,
):
    """Чистый retrieval — релевантные фрагменты корпуса БЕЗ LLM-синтеза.

    Это сырьё для veyra-mcp: сервер отдаёт куски документов, а
    рассуждение (синтез ответа, написание, анализ) делает уже Claude.
    LLM здесь не вызывается — только локальные эмбеддинги + BM25.
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
