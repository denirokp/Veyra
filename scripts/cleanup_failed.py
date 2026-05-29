"""Удалить из workspace документы, у которых не сварился brief (LLM упал на 403/timeout).

Запуск:
    python scripts/cleanup_failed.py --workspace default

После — `python scripts/index_docs.py --sync --workspace default --docs <path>`
догонит удалённые + новые.
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


def _arg(name: str, default: str) -> str:
    if name in sys.argv:
        i = sys.argv.index(name)
        if i + 1 < len(sys.argv):
            return sys.argv[i + 1]
    return default


async def main() -> None:
    workspace = _arg("--workspace", "default")
    await init_db()
    removed: list[str] = []
    async with AsyncSession(engine) as db:
        docs = await list_documents(db, workspace=workspace)
        for d in docs:
            if not d.brief or not d.brief.strip():
                vector_db.delete_document_chunks(d.id, "actual", workspace)
                vector_db.delete_document_chunks(d.id, "archive", workspace)
                await cascade_delete_document(db, d.id)
                removed.append(d.title or d.file_path or d.id)
    print(f"Workspace: {workspace}")
    print(f"Удалено документов без brief: {len(removed)}")
    for name in removed:
        print(f"  - {name}")
    if not removed:
        print("Битых документов не найдено.")


if __name__ == "__main__":
    asyncio.run(main())
