"""Первичная индексация корпуса документов."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from app.rag.indexer import index_document
from app.storage.sql_db import AsyncSession, engine, init_db, create_document
import uuid

CORPUS_DIR = Path("data/corpus")
SUPPORTED = {".pdf", ".docx", ".md", ".txt"}


async def main():
    await init_db()
    files = [f for f in CORPUS_DIR.rglob("*") if f.suffix.lower() in SUPPORTED]
    print(f"Найдено {len(files)} документов")

    async with AsyncSession(engine) as db:
        for f in files:
            print(f"  Индексирую: {f.name} ...", end=" ", flush=True)
            try:
                doc_id = str(uuid.uuid4())
                metadata = {
                    "title": f.stem.replace("_", " "),
                    "status": "actual",
                    "hierarchy_level": 3,
                    "segment": None,
                }
                # Создаём запись документа в БД
                await create_document(db, {
                    "id": doc_id,
                    "title": metadata["title"],
                    "type": "other",
                    "status": metadata["status"],
                    "is_anchor": False,
                    "file_path": str(f),
                    "chunk_count": 0,
                })
                n = await index_document(f, document_id=doc_id, document_metadata=metadata, db=db)
                print(f"{n} чанков")
            except Exception as e:
                print(f"ОШИБКА: {e}")

    print("Готово.")


if __name__ == "__main__":
    asyncio.run(main())
