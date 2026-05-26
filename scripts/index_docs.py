"""Индексация документов из backend/data/docs.

Режимы:
  python scripts/index_docs.py
      ПЕРВИЧНАЯ индексация — сбрасывает datastore (SQLite + Chroma) и
      индексирует всё заново. Для воспроизводимых gate-прогонов.

  python scripts/index_docs.py --sync
      ИНКРЕМЕНТ — базу НЕ сбрасывает. Для каждого файла:
        • новый           → индексирует;
        • изменён (хэш не совпал с уже загруженным) → переиндексирует
          (старые чанки/сущности/сигналы вычищаются каскадно);
        • не изменён      → пропускает.
      Для постепенной загрузки корпуса.

Мультитенантность (PoC):
  --workspace <id>   корпус-владелец (команда/человек). По умолчанию
                     `default`. Корпуса изолированы: отдельная Chroma-
                     коллекция + тег в SQLite. Первичный режим сбрасывает
                     ТОЛЬКО этот workspace, другие не трогает.
  --docs <dir>       каталог документов (по умолчанию backend/data/docs).
                     Удобно держать доки разных корпусов в разных папках.
  --reset-all        полный сброс datastore (файл БД + Chroma) — для
                     чистого первого старта (например, после смены схемы).

  Пример PoC:
    python scripts/index_docs.py --reset-all --workspace teamA --docs data/docs_A
    python scripts/index_docs.py            --workspace teamB --docs data/docs_B
    # запрос к teamA не видит документов teamB

Скрипт переходит в каталог backend/ — относительные пути (БД, Chroma,
docs) резолвятся так же, как при запуске сервера.
"""
import asyncio
import hashlib
import logging
import os
import shutil
import sys
import uuid
from pathlib import Path

BACKEND_DIR = Path(__file__).parent.parent / "backend"
sys.path.insert(0, str(BACKEND_DIR))
os.chdir(BACKEND_DIR)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
for noisy in ("httpx", "httpcore", "chromadb", "sentence_transformers"):
    logging.getLogger(noisy).setLevel(logging.WARNING)

from app.rag.indexer import SUPPORTED_EXTENSIONS as SUPPORTED, index_document
from app.settings import settings
from app.storage import vector_db
from app.storage.sql_db import (
    AsyncSession,
    cascade_delete_document,
    create_document,
    engine,
    init_db,
    list_contradictions,
    list_documents,
    list_logic_signals,
    list_promises,
)

DOCS_DIR = Path(settings.DOCS_DIR)


def _file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


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


async def _index_one(db: AsyncSession, f: Path, workspace: str = "default") -> int:
    """Индексирует один файл как новый документ. Возвращает число чанков."""
    doc_id = str(uuid.uuid4())
    doc = await create_document(
        db,
        {
            "id": doc_id,
            "workspace": workspace,
            "title": f.stem,
            "type": None,
            "status": "actual",
            "is_anchor": False,
            "file_path": str(f),
            "file_hash": _file_hash(f),
            "chunk_count": 0,
        },
    )
    metadata = {
        "document_id": doc_id,
        "title": f.stem,
        "status": "actual",
        "hierarchy_level": doc.hierarchy_level,
    }
    n = await index_document(f, doc_id, metadata, db, workspace=workspace)
    doc.chunk_count = n
    await db.commit()
    return n


def _arg(name: str, default: str) -> str:
    """Достаёт значение флага вида `--name value` из argv."""
    argv = sys.argv[1:]
    if name in argv:
        i = argv.index(name)
        if i + 1 < len(argv):
            return argv[i + 1]
    return default


async def main():
    sync = "--sync" in sys.argv[1:]
    reset_all = "--reset-all" in sys.argv[1:]
    workspace = _arg("--workspace", "default")
    docs_dir = Path(_arg("--docs", str(DOCS_DIR)))

    if reset_all:
        print("Полный сброс datastore (--reset-all):")
        _reset_datastore()
    await init_db()

    print(f"Workspace: {workspace}")
    print(f"Каталог документов: {docs_dir.resolve()}")
    files = [f for f in docs_dir.rglob("*") if f.suffix.lower() in SUPPORTED]
    if sync:
        mode = "инкремент (--sync)"
    elif reset_all:
        mode = "первичный (полный сброс)"
    else:
        mode = f"первичный (сброс workspace '{workspace}')"
    print(f"Найдено {len(files)} файлов · режим: {mode}\n")

    new_n = changed_n = skipped_n = error_n = 0

    async with AsyncSession(engine) as db:
        # Пер-workspace сброс: чистим только этот корпус, другие не трогаем.
        if not sync and not reset_all:
            vector_db.drop_workspace(workspace)
            for d in await list_documents(db, workspace=workspace):
                await cascade_delete_document(db, d.id)

        # В sync-режиме — карты уже загруженных документов по хэшу и пути
        # (только в пределах этого workspace).
        by_hash: dict[str, object] = {}
        by_path: dict[str, object] = {}
        if sync:
            for d in await list_documents(db, workspace=workspace):
                if d.file_hash:
                    by_hash[d.file_hash] = d
                if d.file_path:
                    by_path[d.file_path] = d

        for f in files:
            try:
                if sync:
                    h = _file_hash(f)
                    if h in by_hash:
                        print(f"  = пропуск (не изменён): {f.name}")
                        skipped_n += 1
                        continue
                    old = by_path.get(str(f))
                    if old is not None:
                        print(f"  ~ переиндексация (изменён): {f.name}")
                        vector_db.delete_document_chunks(old.id, "actual", workspace)
                        vector_db.delete_document_chunks(old.id, "archive", workspace)
                        await cascade_delete_document(db, old.id)
                        changed_n += 1
                    else:
                        print(f"  + новый: {f.name}")
                        new_n += 1
                else:
                    print(f"  Индексирую: {f.name} ...", flush=True)
                n = await _index_one(db, f, workspace)
                print(f"  → {n} чанков\n")
            except Exception as e:  # noqa: BLE001
                print(f"  ОШИБКА ({f.name}): {e}\n")
                error_n += 1

        contradictions = await list_contradictions(db)
        signals = await list_logic_signals(db)
        promises = await list_promises(db)

    print("=" * 60)
    if sync:
        print(f"Готово (инкремент). Новых: {new_n}, переиндексировано: "
              f"{changed_n}, пропущено: {skipped_n}, ошибок: {error_n}.")
    else:
        print(f"Готово (первичная индексация). Ошибок: {error_n}.")
    print("Index-time сигналы в базе:")
    print(f"  числовые расхождения : {len(contradictions)}")
    print(f"  логические сигналы   : {len(signals)}")
    print(f"  обещания             : {len(promises)}")
    if not (contradictions or signals or promises):
        if not settings.ENABLE_BACKGROUND_SIGNALS:
            print("  (детекторы отключены: ENABLE_BACKGROUND_SIGNALS=false — "
                  "норма для быстрой загрузки корпуса; «бульон» варится позже)")
        else:
            print("  ⚠️  Все три пусты, хотя ENABLE_BACKGROUND_SIGNALS=true — "
                  "background-skills упали. Смотри INFO-строки 'skill ... → N'.")


if __name__ == "__main__":
    asyncio.run(main())
