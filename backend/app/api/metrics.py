"""System metrics endpoint — реальные счётчики из БД для eval runner и мониторинга."""
from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.storage.sql_db import (
    Chunk,
    Document,
    Entity,
    LogicSignal,
    NumericContradiction,
    Promise,
    get_session,
)

router = APIRouter(tags=["metrics"])


@router.get("/metrics/system")
async def system_metrics(db: AsyncSession = Depends(get_session)):
    """Счётчики корпуса и сигналов для eval runner и дашбордов."""
    total_docs = (await db.execute(select(func.count(Document.id)))).scalar() or 0
    total_chunks = (await db.execute(select(func.count(Chunk.id)))).scalar() or 0
    total_entities = (await db.execute(select(func.count(Entity.id)))).scalar() or 0

    docs_by_status: dict[str, int] = {}
    for status in ("actual", "draft", "archived", "superseded", "unknown"):
        docs_by_status[status] = (
            await db.execute(
                select(func.count(Document.id)).where(Document.status == status)
            )
        ).scalar() or 0

    open_contradictions = (
        await db.execute(
            select(func.count(NumericContradiction.id)).where(
                NumericContradiction.status == "open"
            )
        )
    ).scalar() or 0

    open_signals = (
        await db.execute(
            select(func.count(LogicSignal.id)).where(LogicSignal.status == "open")
        )
    ).scalar() or 0

    promises_open = (
        await db.execute(
            select(func.count(Promise.id)).where(Promise.status == "open")
        )
    ).scalar() or 0

    promises_overdue = (
        await db.execute(
            select(func.count(Promise.id)).where(Promise.status == "overdue")
        )
    ).scalar() or 0

    return {
        "documents": {
            "total": total_docs,
            "by_status": docs_by_status,
        },
        "chunks": {"total": total_chunks},
        "entities": {"total": total_entities},
        "contradictions": {"open": open_contradictions},
        "logic_signals": {"open": open_signals},
        "promises": {"open": promises_open, "overdue": promises_overdue},
    }
