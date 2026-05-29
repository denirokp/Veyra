"""Удалить из БД документы, чей file_path заканчивается на заданное расширение.

Использовать после ручной чистки исходников (например, удалить все
раздутые .docx после декодирования в .txt):

    python scripts/cleanup_by_extension.py --workspace default --ext .docx
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
    ext = _arg("--ext", ".docx").lower()
    if not ext.startswith("."):
        ext = "." + ext
    await init_db()
    removed: list[str] = []
    async with AsyncSession(engine) as db:
        docs = await list_documents(db, workspace=workspace)
        snapshot = [
            (d.id, (d.file_path or ""), (d.title or "")) for d in docs
        ]
        print(f"Workspace: {workspace} — всего документов: {len(snapshot)}")
        for doc_id, file_path, title in snapshot:
            if file_path.lower().endswith(ext):
                vector_db.delete_document_chunks(doc_id, "actual", workspace)
                vector_db.delete_document_chunks(doc_id, "archive", workspace)
                await cascade_delete_document(db, doc_id)
                removed.append(title or file_path or doc_id)
    print(f"Удалено документов с расширением {ext}: {len(removed)}")
    for name in removed[:5]:
        print(f"  - {name}")
    if len(removed) > 5:
        print(f"  ... ещё {len(removed) - 5}")


if __name__ == "__main__":
    asyncio.run(main())
