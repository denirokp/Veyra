"""Document indexer — парсинг → chunking → embedding → сохранение."""
from __future__ import annotations

import uuid
from pathlib import Path

from app.rag.chunker import chunk_document
from app.storage import vector_db


def _parse_text(file_path: Path) -> str:
    suffix = file_path.suffix.lower()
    if suffix == ".pdf":
        import pdfplumber
        with pdfplumber.open(file_path) as pdf:
            return "\n\n".join(p.extract_text() or "" for p in pdf.pages)
    elif suffix == ".docx":
        import docx
        doc = docx.Document(file_path)
        return "\n\n".join(p.text for p in doc.paragraphs)
    elif suffix in (".md", ".txt", ".html"):
        return file_path.read_text(encoding="utf-8")
    else:
        raise ValueError(f"Unsupported format: {suffix}")


async def _embed(texts: list[str]) -> list[list[float]]:
    # TODO: OpenAI text-embedding-3-large через Avito AI proxy
    raise NotImplementedError("Embedding not implemented")


async def index_document(
    file_path: Path,
    document_id: str,
    document_metadata: dict,
) -> int:
    text = _parse_text(file_path)
    chunks = chunk_document(text, document_metadata)

    embeddings = await _embed([c.content for c in chunks])

    collection_name = (
        "actual"
        if document_metadata.get("status") in ("actual", "draft", "unknown")
        else "archive"
    )

    records = [
        {
            "id": str(uuid.uuid4()),
            "content": c.content,
            "embedding": embeddings[i],
            "metadata": {
                **c.metadata,
                "document_id": document_id,
                "chunk_index": c.chunk_index,
            },
        }
        for i, c in enumerate(chunks)
    ]

    vector_db.upsert_chunks(records, collection_name=collection_name)
    return len(chunks)
