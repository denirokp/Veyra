from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.skills.initiative_review import run_initiative_review, run_initiative_review_quick
from app.skills.suggest_missing_metrics import suggest_missing_metrics
from app.storage.sql_db import get_session

router = APIRouter(tags=["initiative"])


class InitiativeReviewRequest(BaseModel):
    title: str
    text: str


@router.post("/initiative-review")
async def initiative_review(
    req: InitiativeReviewRequest,
    db: AsyncSession = Depends(get_session),
):
    return await run_initiative_review(req.title, req.text, db)


@router.post("/initiative-review/quick")
async def initiative_review_quick(
    req: InitiativeReviewRequest,
    db: AsyncSession = Depends(get_session),
):
    """Быстрый предварительный вердикт: verdict + summary + gaps. ~2-4 сек."""
    return await run_initiative_review_quick(req.title, req.text, db)


@router.post("/initiative-review/metrics")
async def suggest_metrics(
    req: InitiativeReviewRequest,
    db: AsyncSession = Depends(get_session),
):
    """Предлагает недостающие KPI для инициативы."""
    return await suggest_missing_metrics(req.title, req.text, db)
