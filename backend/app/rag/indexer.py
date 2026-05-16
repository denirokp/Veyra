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
        return _parse_docx(file_path)
    if suffix in (".md", ".txt", ".html"):
        return file_path.read_text(encoding="utf-8")
    raise ValueError(f"Unsupported format: {suffix}")


def _render_docx_table(table) -> str:
    """Рендерит таблицу построчно в Markdown: каждая строка таблицы — одна
    строка текста, ячейки разделены `|`. Сохраняет привязку значений к
    строке-метрике, которая теряется при плоском обходе."""
    rows: list[str] = []
    for row in table.rows:
        cells = [" ".join(cell.text.split()) for cell in row.cells]
        if not any(cells):
            continue
        rows.append("| " + " | ".join(cells) + " |")
    if not rows:
        return ""
    if len(rows) > 1:
        n_cols = rows[0].count("|") - 1
        rows.insert(1, "| " + " | ".join(["---"] * n_cols) + " |")
    return "\n".join(rows)


def _parse_docx(file_path: Path) -> str:
    """Парсинг .docx с сохранением таблиц.

    `docx.Document.paragraphs` не включает текст внутри таблиц — при наивном
    обходе вся табличная часть (метрики, цифры) теряется. Обходим тело
    документа в порядке следования, рендеря таблицы построчно."""
    import docx as python_docx
    from docx.oxml.table import CT_Tbl
    from docx.oxml.text.paragraph import CT_P
    from docx.table import Table as _DocxTable
    from docx.text.paragraph import Paragraph as _DocxParagraph

    doc = python_docx.Document(file_path)
    blocks: list[str] = []

    for child in doc.element.body.iterchildren():
        if isinstance(child, CT_P):
            para = _DocxParagraph(child, doc)
            text = para.text.strip()
            if not text:
                continue
            style = para.style.name if para.style else ""
            tail = style.split()[-1] if style else ""
            if style.startswith("Heading") and tail.isdigit():
                blocks.append(f"{'#' * int(tail)} {text}")
            else:
                blocks.append(text)
        elif isinstance(child, CT_Tbl):
            rendered = _render_docx_table(_DocxTable(child, doc))
            if rendered:
                blocks.append(rendered)

    return "\n\n".join(blocks)


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

    from app.settings import settings as _settings
    from app.skills.extract_entities import extract_and_save
    from app.skills.track_promises import extract_and_save_promises

    await extract_and_save(text, document_id, document_metadata, db)
    await extract_and_save_promises(text, document_id, document_metadata, db)

    if _settings.ENABLE_BACKGROUND_SIGNALS:
        from app.skills.find_logic_signals import find_logic_signals_for_document
        await find_logic_signals_for_document(document_id, db)

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
