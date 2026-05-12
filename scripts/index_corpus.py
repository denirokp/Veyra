"""Первичная индексация корпуса документов."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from app.rag.indexer import index_document
from app.storage.sql_db import init_db

CORPUS_DIR = Path("data/corpus")
SUPPORTED = {".pdf", ".docx", ".md", ".txt"}


async def main():
    await init_db()
    files = [f for f in CORPUS_DIR.rglob("*") if f.suffix.lower() in SUPPORTED]
    print(f"Найдено {len(files)} документов")

    for f in files:
        print(f"  Индексирую: {f.name} ...", end=" ", flush=True)
        try:
            n = await index_document(f, document_id=str(f.stem), document_metadata={})
            print(f"{n} чанков")
        except Exception as e:
            print(f"ОШИБКА: {e}")

    print("Готово.")


if __name__ == "__main__":
    asyncio.run(main())
