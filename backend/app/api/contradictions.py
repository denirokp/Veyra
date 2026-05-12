from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.schemas import ContradictionPatch
from app.storage.sql_db import get_session, list_contradictions, get_document

router = APIRouter(tags=["contradictions"])


@router.get("/contradictions")
async def get_contradictions(
    status: str | None = None,
    db: AsyncSession = Depends(get_session),
):
    items = await list_contradictions(db, status=status)
    result = []
    for c in items:
        doc_a = await get_document(db, c.document_id_a)
        doc_b = await get_document(db, c.document_id_b)
        result.append({
            "id": c.id,
            "metric": c.metric,
            "value_a": c.value_a,
            "value_b": c.value_b,
            "document_a": {"id": c.document_id_a, "title": doc_a.title if doc_a else c.document_id_a},
            "document_b": {"id": c.document_id_b, "title": doc_b.title if doc_b else c.document_id_b},
            "status": c.status,
            "created_at": c.created_at,
        })
    return result


@router.patch("/contradictions/{contradiction_id}")
async def resolve_contradiction(
    contradiction_id: str,
    patch: ContradictionPatch,
    db: AsyncSession = Depends(get_session),
):
    from sqlalchemy import select, update
    from app.storage.sql_db import Contradiction
    from datetime import datetime

    result = await db.execute(
        select(Contradiction).where(Contradiction.id == contradiction_id)
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
