"""Первичная индексация всех документов в backend/data/docs.

Скрипт переходит в каталог backend/ перед работой, чтобы все относительные
пути (БД, Chroma, docs) резолвились так же, как при запуске сервера из
backend/ — иначе индексация писала бы в другую базу, чем читает API."""
import asyncio
import os
import sys
import uuid
from pathlib import Path

BACKEND_DIR = Path(__file__).parent.parent / "backend"
sys.path.insert(0, str(BACKEND_DIR))
os.chdir(BACKEND_DIR)

from app.rag.indexer import SUPPORTED_EXTENSIONS as SUPPORTED, index_document
from app.settings import settings
from app.storage.sql_db import AsyncSession, create_document, engine, init_db

DOCS_DIR = Path(settings.DOCS_DIR)


async def main():
    await init_db()
    print(f"Каталог документов: {DOCS_DIR.resolve()}")
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
