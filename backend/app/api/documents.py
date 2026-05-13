from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.schemas import DocumentOut, DocumentPatch, DocumentStatus, DocumentType
from app.rag.indexer import index_document, reindex_document, SUPPORTED_EXTENSIONS
from app.settings import settings
from app.storage.sql_db import (
    AsyncSession as DbSession,
    create_document,
    engine,
    get_document,
    list_documents,
    update_document,
    get_session,
)

router = APIRouter(tags=["documents"])

CORPUS_DIR = Path(settings.CORPUS_DIR)
CORPUS_DIR.mkdir(parents=True, exist_ok=True)


def _to_out(doc) -> DocumentOut:
    return DocumentOut(
        id=doc.id,
        title=doc.title,
        type=doc.type,
        status=doc.status,
        hierarchy_level=doc.hierarchy_level,
        segment=doc.segment,
        author=doc.author,
        created_at=doc.created_at,
        is_anchor=doc.is_anchor or False,
        is_style_anchor=doc.is_style_anchor or False,
        confluence_url=doc.confluence_url,
        chunk_count=doc.chunk_count,
        indexed_at=doc.indexed_at,
    )


@router.post("/documents", response_model=DocumentOut)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    title: Optional[str] = Form(None),
    doc_type: Optional[str] = Form(None),
    segment: Optional[str] = Form(None),
    author: Optional[str] = Form(None),
    status: str = Form("unknown"),
    is_anchor: bool = Form(False),
    confluence_url: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_session),
):
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        raise HTTPException(400, f"Неподдерживаемый формат: {suffix}")

    doc_id = str(uuid.uuid4())
    file_path = CORPUS_DIR / f"{doc_id}{suffix}"

    # Сохраняем файл
    with file_path.open("wb") as f:
        shutil.copyfileobj(file.file, f)

    doc_title = title or Path(file.filename or "").stem

    doc = await create_document(
        db,
        {
            "id": doc_id,
            "title": doc_title,
            "type": doc_type,
            "segment": segment,
            "author": author,
            "status": status,
            "is_anchor": is_anchor,
            "confluence_url": confluence_url,
            "file_path": str(file_path),
            "chunk_count": 0,
        },
    )

    # Индексация в фоне
    metadata = {
        "document_id": doc_id,
        "title": doc_title,
        "status": status,
        "segment": segment,
        "hierarchy_level": doc.hierarchy_level,
    }
    background_tasks.add_task(_index_in_background, file_path, doc_id, metadata)

    return _to_out(doc)


async def _index_in_background(
    file_path: Path,
    doc_id: str,
    metadata: dict,
) -> None:
    # Request-scoped session уже закрыта когда фон стартует — открываем свою.
    async with DbSession(engine) as db:
        try:
            n_chunks = await index_document(file_path, doc_id, metadata, db)
            await update_document(db, doc_id, {"chunk_count": n_chunks})
        except Exception as e:
            import logging
            logging.getLogger(__name__).error("Index error doc=%s: %s", doc_id, e)


@router.get("/documents", response_model=list[DocumentOut])
async def list_docs(
    status: Optional[str] = None,
    segment: Optional[str] = None,
    db: AsyncSession = Depends(get_session),
):
    docs = await list_documents(db, status=status, segment=segment)
    return [_to_out(d) for d in docs]


@router.get("/documents/{doc_id}", response_model=DocumentOut)
async def get_doc(doc_id: str, db: AsyncSession = Depends(get_session)):
    doc = await get_document(db, doc_id)
    if not doc:
        raise HTTPException(404, "Документ не найден")
    return _to_out(doc)


@router.patch("/documents/{doc_id}", response_model=DocumentOut)
async def patch_doc(
    doc_id: str,
    patch: DocumentPatch,
    db: AsyncSession = Depends(get_session),
):
    changes = patch.model_dump(exclude_none=True)
    if "superseded_by" in changes:
        changes["superseded_by"] = str(changes["superseded_by"])

    doc = await update_document(db, doc_id, changes)
    if not doc:
        raise HTTPException(404, "Документ не найден")

    # Если статус изменился — переиндексируем
    if "status" in changes:
        await reindex_document(doc_id, changes["status"], db)

    return _to_out(doc)


@router.delete("/documents/{doc_id}")
async def delete_doc(doc_id: str, db: AsyncSession = Depends(get_session)):
    from app.storage import vector_db
    from sqlalchemy import delete
    from app.storage.sql_db import Document, Chunk

    doc = await get_document(db, doc_id)
    if not doc:
        raise HTTPException(404, "Документ не найден")

    vector_db.delete_document_chunks(doc_id, "actual")
    vector_db.delete_document_chunks(doc_id, "archive")

    await db.execute(delete(Chunk).where(Chunk.document_id == doc_id))
    await db.execute(delete(Document).where(Document.id == doc_id))
    await db.commit()

    return {"deleted": doc_id}
