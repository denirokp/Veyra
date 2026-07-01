from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.schemas import PromisePatch
from app.topic_filter import filter_rows_by_query
from app.storage.sql_db import get_session, list_promises, get_document

router = APIRouter(tags=["promises"])


async def _relevant_docs(query: str | None) -> set[str] | None:
    """Семантически релевантные doc_id по теме — для фильтра (ловит синонимы).
    None при пустом query или недоступном ретривере (деградация до токен-матча)."""
    if not query or not query.strip():
        return None
    try:
        from app.rag.retriever import relevant_document_ids
        return await relevant_document_ids(query)
    except Exception:  # noqa: BLE001
        return None


@router.get("/promises")
async def get_promises(
    status: str | None = None,
    query: str | None = None,
    db: AsyncSession = Depends(get_session),
):
    items = await list_promises(db, status=status)
    result = []
    for p in items:
        doc = await get_document(db, p.document_id)
        result.append({
            "id": p.id,
            "text": p.text,
            "normalized_text": p.normalized_text,
            "document": {"id": p.document_id, "title": doc.title if doc else p.document_id},
            "document_date": p.document_date,
            "deadline": p.deadline,
            "metric": p.metric,
            "target_value": p.target_value,
            "status": p.status,
            "resolved_at": p.resolved_at,
            "notes": p.notes,
        })
    rel = await _relevant_docs(query)
    return filter_rows_by_query(
        result, query,
        lambda r: " ".join(str(x) for x in (
            r["text"], r["normalized_text"], r["metric"], r["document"]["title"])),
        relevant_doc_ids=rel,
        doc_ids_of=lambda r: (r["document"]["id"],),
    )


@router.patch("/promises/{promise_id}")
async def update_promise(
    promise_id: str,
    patch: PromisePatch,
    db: AsyncSession = Depends(get_session),
):
    from sqlalchemy import select
    from app.storage.sql_db import Promise

    result = await db.execute(select(Promise).where(Promise.id == promise_id))
    p = result.scalar_one_or_none()
    if not p:
        raise HTTPException(404, "Обещание не найдено")

    p.status = patch.status.value
    if patch.resolved_at:
        p.resolved_at = patch.resolved_at
    if patch.notes:
        p.notes = patch.notes
    await db.commit()
    return {"id": promise_id, "status": p.status}
