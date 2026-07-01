"""Точечно удалить документы из корпуса по id.

Каскадно чистит и Chroma (чанки в actual/archive), и SQLite (документ,
сущности, обещания, числовые/логические связи) через cascade_delete_document.
Нужен для удаления мусорных/раздутых доков без полной переиндексации.

    python scripts/delete_docs.py <doc_id> [<doc_id> ...] [--workspace default]

Полные id берутся из scripts/... size-запроса или list_documents.
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(BACKEND_DIR))
os.chdir(BACKEND_DIR)

from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402

from app.storage import vector_db  # noqa: E402
from app.storage.sql_db import (  # noqa: E402
    cascade_delete_document,
    engine,
    init_db,
    list_documents,
)


def _parse_args() -> tuple[list[str], str]:
    workspace = "default"
    ids: list[str] = []
    argv = sys.argv[1:]
    i = 0
    while i < len(argv):
        if argv[i] == "--workspace" and i + 1 < len(argv):
            workspace = argv[i + 1]
            i += 2
            continue
        ids.append(argv[i])
        i += 1
    return ids, workspace


async def main() -> None:
    ids, workspace = _parse_args()
    if not ids:
        print("Укажи хотя бы один doc_id:\n"
              "  python scripts/delete_docs.py <id> [<id> ...] [--workspace default]")
        return

    await init_db()
    async with AsyncSession(engine) as db:
        docs = await list_documents(db, workspace=workspace)
        title_by_id = {d.id: (d.title or "") for d in docs}

        removed: list[tuple[str, str]] = []
        missing: list[str] = []
        for doc_id in ids:
            if doc_id not in title_by_id:
                missing.append(doc_id)
                continue
            vector_db.delete_document_chunks(doc_id, "actual", workspace)
            vector_db.delete_document_chunks(doc_id, "archive", workspace)
            await cascade_delete_document(db, doc_id)
            removed.append((doc_id, title_by_id[doc_id]))

    print(f"Workspace: {workspace}")
    print(f"Удалено: {len(removed)}")
    for doc_id, title in removed:
        print(f"  - {title}  [{doc_id}]")
    if missing:
        print(f"Не найдено в workspace ({len(missing)}):")
        for doc_id in missing:
            print(f"  ? {doc_id}")


if __name__ == "__main__":
    asyncio.run(main())
