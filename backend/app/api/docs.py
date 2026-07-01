import time

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.skills.build_graph import build_document_graph
from app.skills.find_gaps import find_gaps
from app.storage.sql_db import Document, NumericContradiction, LogicSignal, Promise, get_session

router = APIRouter(tags=["docs"])

# In-memory кэш /docs/stats — фронт поллит его раз в секунду, а внутри 6 COUNT'ов
# по SQLite. TTL 10 секунд — небольшое отставание (бары обновятся не моментально),
# зато нагрузка на БД падает на порядок.
_stats_cache: dict = {"data": None, "expires_at": 0.0}
_STATS_TTL = 10.0


@router.get("/docs/stats")
async def docs_stats(db: AsyncSession = Depends(get_session)):
    now = time.monotonic()
    if _stats_cache["data"] is not None and now < _stats_cache["expires_at"]:
        return _stats_cache["data"]

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

    open_numeric = (
        await db.execute(
            select(func.count(NumericContradiction.id)).where(NumericContradiction.status == "open")
        )
    ).scalar()

    open_logic = (
        await db.execute(
            select(func.count(LogicSignal.id)).where(LogicSignal.status == "open")
        )
    ).scalar()

    open_promises = (
        await db.execute(
            select(func.count(Promise.id)).where(Promise.status == "open")
        )
    ).scalar()

    # Свежесть корпуса: когда последний документ был проиндексирован. Нужно
    # навыку для «контракта охвата» — предвычисленные таблицы find_* отражают
    # состояние корпуса на этот момент, а не «сейчас».
    last_indexed = (
        await db.execute(select(func.max(Document.indexed_at)))
    ).scalar()

    payload = {
        "total_documents": total,
        "by_status": by_status,
        "anchor_documents": anchors,
        "open_contradictions": open_numeric,
        "open_logic_signals": open_logic,
        "open_promises": open_promises,
        "last_indexed_at": last_indexed.isoformat() if last_indexed else None,
    }
    _stats_cache["data"] = payload
    _stats_cache["expires_at"] = now + _STATS_TTL
    return payload


def invalidate_stats_cache() -> None:
    """Сбрасывает кэш — вызывается при upload/delete документа."""
    _stats_cache["data"] = None
    _stats_cache["expires_at"] = 0.0


@router.get("/docs/gaps")
async def get_gaps(db: AsyncSession = Depends(get_session)):
    """Серые зоны — темы в документах, отсутствующие в текущей стратегии."""
    return await find_gaps(db)


@router.get("/docs/graph")
async def get_graph(db: AsyncSession = Depends(get_session)):
    """Граф связей между документами — узлы и рёбра по общим сущностям."""
    return await build_document_graph(db)
