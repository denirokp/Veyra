"""Document indexer — парсинг → chunking → embedding → skills → сохранение."""
from __future__ import annotations

import uuid
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.clients import embed
from app.rag.chunker import Chunk, chunk_document
from app.storage import vector_db
from app.storage.sql_db import save_chunks


SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".md", ".txt", ".html"}


def parse_text(file_path: Path) -> str:
    suffix = file_path.suffix.lower()
    if suffix == ".pdf":
        import pdfplumber
        with pdfplumber.open(file_path) as pdf:
            pages = [p.extract_text() or "" for p in pdf.pages]
        return "\n\n".join(pages)
    if suffix == ".docx":
        import docx as python_docx
        doc = python_docx.Document(file_path)
        paragraphs = []
        for para in doc.paragraphs:
            if para.text.strip():
                if para.style.name.startswith("Heading"):
                    level = para.style.name.split()[-1]
                    paragraphs.append(f"{'#' * int(level)} {para.text}")
                else:
                    paragraphs.append(para.text)
        return "\n\n".join(paragraphs)
    if suffix in (".md", ".txt", ".html"):
        return file_path.read_text(encoding="utf-8")
    raise ValueError(f"Unsupported format: {suffix}")


def _collection_for_status(status: str) -> str:
    if status == "archived":
        return "archive"
    return "actual"  # actual, draft, unknown → в основную коллекцию


async def index_document(
    file_path: Path,
    document_id: str,
    document_metadata: dict,
    db: AsyncSession,
) -> int:
    """
    Полный пайплайн индексации:
    1. Парсинг
    2. Chunking
    3. Embedding
    4. Сохранение в ChromaDB
    5. Сохранение чанков в SQLite
    6. Skills: extract_entities, track_promises
    """
    text = parse_text(file_path)
    chunks: list[Chunk] = chunk_document(text, document_metadata)

    if not chunks:
        return 0

    # Батчинг эмбеддингов (не более 100 за раз)
    batch_size = 100
    embeddings: list[list[float]] = []
    for i in range(0, len(chunks), batch_size):
        batch_texts = [c.content for c in chunks[i : i + batch_size]]
        embeddings.extend(await embed(batch_texts))

    collection_name = _collection_for_status(document_metadata.get("status", "unknown"))

    chunk_ids = [str(uuid.uuid4()) for _ in chunks]

    # Сохраняем в ChromaDB (только не superseded)
    if document_metadata.get("status") != "superseded":
        vector_db.upsert_chunks(
            [
                {
                    "id": chunk_ids[i],
                    "content": c.content,
                    "embedding": embeddings[i],
                    "metadata": {
                        **c.metadata,
                        "document_id": document_id,
                        "title": document_metadata.get("title", ""),
                        "chunk_index": c.chunk_index,
                        "hierarchy_level": document_metadata.get("hierarchy_level", 5),
                        "status": document_metadata.get("status", "unknown"),
                    },
                }
                for i, c in enumerate(chunks)
            ],
            collection_name=collection_name,
        )

    # Сохраняем чанки в SQLite
    await save_chunks(
        db,
        [
            {
                "id": chunk_ids[i],
                "document_id": document_id,
                "content": c.content,
                "section": c.section,
                "subsection": c.subsection,
                "chunk_index": c.chunk_index,
                "token_count": c.token_count,
                "embedding_id": chunk_ids[i],
                "metadata_": c.metadata,
            }
            for i, c in enumerate(chunks)
        ],
    )

    # Skills pipeline — изолируем каждый skill, чтобы падение одного не
    # уносило за собой обновление chunk_count и другие skills.
    import logging as _logging
    _log = _logging.getLogger(__name__)
    from app.skills.extract_entities import extract_and_save
    from app.skills.track_promises import extract_and_save_promises
    from app.skills.find_logic_signals import find_logic_signals_for_document

    for skill_name, coro in (
        ("extract_entities", extract_and_save(text, document_id, document_metadata, db)),
        ("track_promises", extract_and_save_promises(text, document_id, document_metadata, db)),
        ("find_logic_signals", find_logic_signals_for_document(document_id, db)),
    ):
        try:
            await coro
        except Exception as exc:
            _log.exception("skill %s failed for doc=%s: %s", skill_name, document_id, exc)

    return len(chunks)


async def reindex_document(
    document_id: str,
    new_status: str,
    db: AsyncSession,
) -> None:
    """Перемещает чанки между коллекциями при смене статуса."""
    from sqlalchemy import select
    from app.storage.sql_db import Chunk as ChunkRow, Document

    # Удаляем из обеих коллекций
    vector_db.delete_document_chunks(document_id, "actual")
    vector_db.delete_document_chunks(document_id, "archive")

    if new_status == "superseded":
        return  # superseded не индексируется

    # Получаем чанки и переиндексируем
    result = await db.execute(
        select(ChunkRow).where(ChunkRow.document_id == document_id)
    )
    chunk_rows = list(result.scalars().all())
    if not chunk_rows:
        return

    texts = [c.content for c in chunk_rows]
    embeddings = await embed(texts)
    collection = _collection_for_status(new_status)

    vector_db.upsert_chunks(
        [
            {
                "id": c.id,
                "content": c.content,
                "embedding": embeddings[i],
                "metadata": {**(c.metadata_ or {}), "status": new_status},
            }
            for i, c in enumerate(chunk_rows)
        ],
        collection_name=collection,
    )
