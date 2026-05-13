from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.schemas import ContradictionPatch
from app.storage.sql_db import (
    get_session,
    get_document,
    list_contradictions,
    list_logic_signals,
    LogicSignal,
    NumericContradiction,
)

router = APIRouter(tags=["contradictions"])


# ── Numeric contradictions ────────────────────────────────────────────────────

@router.get("/contradictions/numeric")
async def get_numeric_contradictions(
    status: str | None = None,
    db: AsyncSession = Depends(get_session),
):
    items = await list_contradictions(db, status=status)
    result = []
    for c in items:
        doc_a = await get_document(db, c.document_id_a)
        doc_b = await get_document(db, c.document_id_b)
        # Пропускаем legacy-осиротевшие расхождения: оба документа удалены.
        if not doc_a and not doc_b:
            continue
        result.append({
            "id": c.id,
            "metric": c.metric,
            "value_a": c.value_a,
            "value_b": c.value_b,
            "period": c.period,
            "document_a": {
                "id": c.document_id_a,
                "title": doc_a.title if doc_a else "Документ удалён",
                "hierarchy_level": doc_a.hierarchy_level if doc_a else None,
            },
            "document_b": {
                "id": c.document_id_b,
                "title": doc_b.title if doc_b else "Документ удалён",
                "hierarchy_level": doc_b.hierarchy_level if doc_b else None,
            },
            "status": c.status,
            "created_at": c.created_at,
        })
    return result


@router.patch("/contradictions/numeric/{contradiction_id}")
async def resolve_numeric_contradiction(
    contradiction_id: str,
    patch: ContradictionPatch,
    db: AsyncSession = Depends(get_session),
):
    from sqlalchemy import select
    from datetime import datetime

    result = await db.execute(
        select(NumericContradiction).where(NumericContradiction.id == contradiction_id)
    )
    c = result.scalar_one_or_none()
    if not c:
        raise HTTPException(404, "Расхождение не найдено")

    c.status = patch.status.value
    if patch.resolved_by:
        c.resolved_by = str(patch.resolved_by)
    c.resolved_at = datetime.utcnow()
    await db.commit()
    return {"id": contradiction_id, "status": c.status}


# ── Backward-compat: старые пути без /numeric ─────────────────────────────────

@router.get("/contradictions")
async def get_contradictions_compat(
    status: str | None = None,
    db: AsyncSession = Depends(get_session),
):
    return await get_numeric_contradictions(status=status, db=db)


@router.patch("/contradictions/{contradiction_id}")
async def resolve_contradiction_compat(
    contradiction_id: str,
    patch: ContradictionPatch,
    db: AsyncSession = Depends(get_session),
):
    return await resolve_numeric_contradiction(
        contradiction_id=contradiction_id, patch=patch, db=db
    )


# ── Logic signals ─────────────────────────────────────────────────────────────

@router.get("/contradictions/logic")
async def get_logic_signals(
    status: str | None = None,
    db: AsyncSession = Depends(get_session),
):
    items = await list_logic_signals(db, status=status)
    result = []
    for s in items:
        doc_a = await get_document(db, s.document_id_a)
        doc_b = await get_document(db, s.document_id_b)
        # Пропускаем legacy-осиротевшие сигналы.
        if not doc_a and not doc_b:
            continue
        result.append({
            "id": s.id,
            "signal_type": s.signal_type,
            "statement_a": s.statement_a,
            "statement_b": s.statement_b,
            "document_a": {
                "id": s.document_id_a,
                "title": doc_a.title if doc_a else "Документ удалён",
                "hierarchy_level": doc_a.hierarchy_level if doc_a else None,
                "created_at": str(doc_a.created_at) if doc_a and doc_a.created_at else None,
            },
            "document_b": {
                "id": s.document_id_b,
                "title": doc_b.title if doc_b else "Документ удалён",
                "hierarchy_level": doc_b.hierarchy_level if doc_b else None,
                "created_at": str(doc_b.created_at) if doc_b and doc_b.created_at else None,
            },
            "confidence": s.confidence,
            "status": s.status,
            "review_notes": s.review_notes,
            "created_at": s.created_at,
        })
    return result


@router.patch("/contradictions/logic/{signal_id}")
async def update_logic_signal(
    signal_id: str,
    status: str,
    review_notes: str | None = None,
    db: AsyncSession = Depends(get_session),
):
    from sqlalchemy import select

    result = await db.execute(select(LogicSignal).where(LogicSignal.id == signal_id))
    s = result.scalar_one_or_none()
    if not s:
        raise HTTPException(404, "Сигнал не найден")

    allowed = {"open", "reviewed", "dismissed"}
    if status not in allowed:
        raise HTTPException(422, f"status must be one of {allowed}")

    s.status = status
    if review_notes:
        s.review_notes = review_notes
    await db.commit()
    return {"id": signal_id, "status": s.status}
