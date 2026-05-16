"""Первичная индексация всех документов в backend/data/docs.

Скрипт переходит в каталог backend/ перед работой, чтобы все относительные
пути (БД, Chroma, docs) резолвились так же, как при запуске сервера из
backend/ — иначе индексация писала бы в другую базу, чем читает API.

ВАЖНО: это скрипт ПЕРВИЧНОЙ индексации — он сбрасывает datastore (SQLite +
Chroma) перед прогоном. Запускать повторно безопасно: каждый прогон даёт
чистое детерминированное состояние, без дублей документов.
"""
import asyncio
import logging
import os
import shutil
import sys
import uuid
from pathlib import Path

BACKEND_DIR = Path(__file__).parent.parent / "backend"
sys.path.insert(0, str(BACKEND_DIR))
os.chdir(BACKEND_DIR)

# INFO-логи индексатора и skills видны в выводе — чтобы понимать, что
# реально записалось (entities/promises/logic signals) и где упало.
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
for noisy in ("httpx", "httpcore", "chromadb", "sentence_transformers"):
    logging.getLogger(noisy).setLevel(logging.WARNING)

from app.rag.indexer import SUPPORTED_EXTENSIONS as SUPPORTED, index_document
from app.settings import settings
from app.storage.sql_db import (
    AsyncSession,
    create_document,
    engine,
    init_db,
    list_contradictions,
    list_logic_signals,
    list_promises,
)

DOCS_DIR = Path(settings.DOCS_DIR)


def _reset_datastore() -> None:
    """Удаляет SQLite-файл и каталог Chroma — чистый старт без дублей."""
    db_path = Path(settings.DATABASE_URL.split(":///")[-1])
    for p in (db_path, Path(f"{db_path}-wal"), Path(f"{db_path}-shm")):
        if p.exists():
            p.unlink()
            print(f"  сброшено: {p}")
    chroma_dir = Path(settings.CHROMA_PERSIST_DIR)
    if chroma_dir.exists():
        shutil.rmtree(chroma_dir)
        print(f"  сброшено: {chroma_dir}/")


async def main():
    print("Сброс datastore перед первичной индексацией:")
    _reset_datastore()

    await init_db()
    print(f"Каталог документов: {DOCS_DIR.resolve()}")
    files = [f for f in DOCS_DIR.rglob("*") if f.suffix.lower() in SUPPORTED]
    print(f"Найдено {len(files)} документов\n")

    async with AsyncSession(engine) as db:
        for f in files:
            print(f"  Индексирую: {f.name} ...", flush=True)
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
                print(f"  → {n} чанков\n")
            except Exception as e:
                print(f"  ОШИБКА: {e}\n")

        # Итоговая сводка — сразу видно, сварился ли «бульон».
        contradictions = await list_contradictions(db)
        signals = await list_logic_signals(db)
        promises = await list_promises(db)

    print("=" * 60)
    print("Готово. Index-time сигналы:")
    print(f"  числовые расхождения : {len(contradictions)}")
    print(f"  логические сигналы   : {len(signals)}")
    print(f"  обещания             : {len(promises)}")
    if not (contradictions or signals or promises):
        print("  ⚠️  Все три пусты — background-skills ничего не записали. "
              "Смотри INFO-строки 'skill ... → N' выше.")


if __name__ == "__main__":
    asyncio.run(main())
