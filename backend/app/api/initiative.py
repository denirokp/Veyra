from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.skills.initiative_review import run_initiative_review
from app.skills.suggest_missing_metrics import suggest_missing_metrics
from app.storage.sql_db import get_session

router = APIRouter(tags=["initiative"])


class InitiativeReviewRequest(BaseModel):
    # Защита от случайного 10MB body — LLM-контекст разнесёт.
    title: str = Field(..., min_length=1, max_length=500)
    text: str = Field(..., max_length=50_000)


@router.post("/initiative-review")
async def initiative_review(
    req: InitiativeReviewRequest,
    db: AsyncSession = Depends(get_session),
):
    return await run_initiative_review(req.title, req.text, db)


@router.post("/initiative-review/metrics")
async def suggest_metrics(
    req: InitiativeReviewRequest,
    db: AsyncSession = Depends(get_session),
):
    """Предлагает недостающие KPI для инициативы."""
    return await suggest_missing_metrics(req.title, req.text, db)
