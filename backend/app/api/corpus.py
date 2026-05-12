from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.skills.find_gaps import find_gaps
from app.storage.sql_db import Document, Contradiction, Promise, get_session

router = APIRouter(tags=["corpus"])


@router.get("/corpus/stats")
async def corpus_stats(db: AsyncSession = Depends(get_session)):
    total = (await db.execute(select(func.count(Document.id)))).scalar()
    by_status = {}
    for status in ("actual", "draft", "archived", "superseded", "unknown"):
        count = (
            await db.execute(
                select(func.count(Document.id)).where(Document.status == status)
            )
        ).scalar()
        by_status[status] = count

    anchors = (
        await db.execute(
            select(func.count(Document.id)).where(Document.is_anchor == True)
        )
    ).scalar()

    open_contradictions = (
        await db.execute(
            select(func.count(Contradiction.id)).where(Contradiction.status == "open")
        )
    ).scalar()

    open_promises = (
        await db.execute(
            select(func.count(Promise.id)).where(Promise.status == "open")
        )
    ).scalar()

    return {
        "total_documents": total,
        "by_status": by_status,
        "anchor_documents": anchors,
        "open_contradictions": open_contradictions,
        "open_promises": open_promises,
    }


@router.get("/corpus/gaps")
async def get_gaps(db: AsyncSession = Depends(get_session)):
    """Серые зоны — темы в корпусе, отсутствующие в текущей стратегии."""
    return await find_gaps(db)
