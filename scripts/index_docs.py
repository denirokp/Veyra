"""Первичная индексация всех документов в data/docs."""
import asyncio
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from app.rag.indexer import index_document
from app.storage.sql_db import AsyncSession, create_document, engine, init_db

DOCS_DIR = Path("data/docs")
SUPPORTED = {".pdf", ".docx", ".md", ".txt"}


async def main():
    await init_db()
    files = [f for f in DOCS_DIR.rglob("*") if f.suffix.lower() in SUPPORTED]
    print(f"Найдено {len(files)} документов")

    async with AsyncSession(engine) as db:
        for f in files:
            print(f"  Индексирую: {f.name} ...", end=" ", flush=True)
            try:
                doc_id = str(uuid.uuid4())
                doc = await create_document(
                    db,
                    {
                        "id": doc_id,
                        "title": f.stem,
                        "type": None,
                        "status": "actual",
                        "is_anchor": False,
                        "file_path": str(f),
                        "chunk_count": 0,
                    },
                )
                metadata = {
                    "document_id": doc_id,
                    "title": f.stem,
                    "status": "actual",
                    "hierarchy_level": doc.hierarchy_level,
                }
                n = await index_document(f, doc_id, metadata, db)
                doc.chunk_count = n
                await db.commit()
                print(f"{n} чанков")
            except Exception as e:
                print(f"ОШИБКА: {e}")

    print("Готово.")


if __name__ == "__main__":
    asyncio.run(main())
