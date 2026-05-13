import logging

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents import orchestrator
from app.models.schemas import ChatRequest, ChatResponse
from app.storage.sql_db import get_session

logger = logging.getLogger(__name__)
router = APIRouter(tags=["chat"])


@router.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    db: AsyncSession = Depends(get_session),
) -> ChatResponse:
    try:
        return await orchestrator.run(request, db=db)
    except Exception as exc:
        logger.exception("Chat request failed: %s", exc)
        return ChatResponse(
            answer="Сервис временно недоступен. Попробуйте ещё раз через несколько секунд.",
            facts=[],
            hypotheses=[],
            warnings=["⚠️ Произошла внутренняя ошибка при обработке запроса"],
            requires_verification=[],
            metadata={"error": type(exc).__name__},
        )
