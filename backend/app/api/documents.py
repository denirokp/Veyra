from __future__ import annotations

import hashlib
import json
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

DOCS_DIR = Path(settings.DOCS_DIR)
DOCS_DIR.mkdir(parents=True, exist_ok=True)

# Лимит размера загружаемого файла (100 МБ). Не пускаем больше — экономим память
# при embedding и защищаемся от ситуации «случайный 10ГБ-файл уронил процесс».
MAX_UPLOAD_BYTES = 100 * 1024 * 1024

# Белый список MIME — UploadFile.content_type может быть подделан клиентом,
# но мы всё равно фильтруем явный мусор. Главная защита — суффикс файла
# в SUPPORTED_EXTENSIONS + сам парсер, который кинет ValueError на не-документ.
_ALLOWED_MIME_PREFIXES = (
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/msword",  # старый .doc — мы не парсим, но не отбрасываем хедер
    "application/octet-stream",  # старые браузеры так маркируют .docx/.md/.txt
    "text/",
)


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
    # Имя файла используем только для extension и title — path-traversal
    # невозможен, потому что target пишем как DOCS_DIR / f"{uuid}{suffix}".
    raw_name = file.filename or ""
    suffix = Path(raw_name).suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        raise HTTPException(400, f"Неподдерживаемый формат: {suffix}")

    ctype = (file.content_type or "").lower()
    if ctype and not any(ctype.startswith(p) for p in _ALLOWED_MIME_PREFIXES):
        raise HTTPException(415, f"Неподдерживаемый MIME-тип: {ctype}")

    doc_id = str(uuid.uuid4())
    file_path = DOCS_DIR / f"{doc_id}{suffix}"

    # Стримим в файл с проверкой кумулятивного размера и считаем SHA-256
    # для дедупликации повторных загрузок.
    bytes_written = 0
    hasher = hashlib.sha256()
    with file_path.open("wb") as f:
        while True:
            chunk = await file.read(1024 * 1024)  # 1 МБ за раз
            if not chunk:
                break
            bytes_written += len(chunk)
            if bytes_written > MAX_UPLOAD_BYTES:
                f.close()
                file_path.unlink(missing_ok=True)
                raise HTTPException(
                    413,
                    f"Файл больше лимита {MAX_UPLOAD_BYTES // (1024 * 1024)} МБ",
                )
            hasher.update(chunk)
            f.write(chunk)

    file_hash = hasher.hexdigest()

    # Дедупликация: тот же контент уже грузили — возвращаем существующий
    # документ и удаляем дубль с диска (он бы запустил повторную индексацию).
    from app.storage.sql_db import get_document_by_hash
    existing = await get_document_by_hash(db, file_hash)
    if existing:
        file_path.unlink(missing_ok=True)
        return _to_out(existing)

    doc_title = title or Path(raw_name).stem or "Без названия"

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
            "file_hash": file_hash,
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

    from app.api.docs import invalidate_stats_cache
    invalidate_stats_cache()

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


@router.post("/documents/{doc_id}/reindex", response_model=DocumentOut)
async def reindex_doc(
    doc_id: str,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_session),
):
    """Перезапустить индексацию документа — например после правки парсера
    или если предыдущий прогон упал. Очищает старые чанки из Chroma и SQL
    и стартует новую индексацию по сохранённому файлу на диске."""
    from app.storage import vector_db
    from sqlalchemy import delete
    from app.storage.sql_db import Chunk as ChunkRow

    doc = await get_document(db, doc_id)
    if not doc:
        raise HTTPException(404, "Документ не найден")
    if not doc.file_path or not Path(doc.file_path).exists():
        raise HTTPException(409, "Файл документа недоступен на диске")

    # Чистим только чанки и связанные индексы — сам Document, entities,
    # promises и contradictions оставляем (они частично могут быть useful).
    vector_db.delete_document_chunks(doc_id, "actual")
    vector_db.delete_document_chunks(doc_id, "archive")
    await db.execute(delete(ChunkRow).where(ChunkRow.document_id == doc_id))
    await update_document(db, doc_id, {"chunk_count": 0})
    await db.commit()

    metadata = {
        "document_id": doc_id,
        "title": doc.title,
        "status": doc.status,
        "segment": doc.segment,
        "hierarchy_level": doc.hierarchy_level,
    }
    background_tasks.add_task(_index_in_background, Path(doc.file_path), doc_id, metadata)

    return _to_out(doc)


@router.delete("/documents/{doc_id}")
async def delete_doc(doc_id: str, db: AsyncSession = Depends(get_session)):
    from app.storage import vector_db
    from app.storage.sql_db import cascade_delete_document

    doc = await get_document(db, doc_id)
    if not doc:
        raise HTTPException(404, "Документ не найден")

    file_path = doc.file_path

    # 1. Чанки из Chroma (обе коллекции — может быть в любой)
    vector_db.delete_document_chunks(doc_id, "actual")
    vector_db.delete_document_chunks(doc_id, "archive")

    # 2. SQL — каскадно удалить entities/promises/contradictions/signals/relations/chunks
    await cascade_delete_document(db, doc_id)

    # 3. Файл на диске
    if file_path:
        try:
            Path(file_path).unlink(missing_ok=True)
        except OSError:
            # Не критично — оставшийся файл не ломает работу системы
            pass

    from app.api.docs import invalidate_stats_cache
    invalidate_stats_cache()

    return {"deleted": doc_id}
