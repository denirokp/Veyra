from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.skills.initiative_review import run_initiative_review
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
