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
