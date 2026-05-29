"""Удалить из БД документы, чей file_path больше не существует на диске.

Нужно после ручного удаления исходников (например, замены раздутых .docx
на чистые .txt после `decode_confluence_mhtml.py`): без этого в БД
останутся осиротевшие документы с мёртвыми ссылками.

    python scripts/cleanup_missing.py --workspace default
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

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
            path = d.file_path
            if not path:
                continue
            if not Path(path).exists():
                vector_db.delete_document_chunks(d.id, "actual", workspace)
                vector_db.delete_document_chunks(d.id, "archive", workspace)
                await cascade_delete_document(db, d.id)
                removed.append(d.title or path)
    print(f"Workspace: {workspace}")
    print(f"Удалено документов с отсутствующим файлом: {len(removed)}")
    for name in removed:
        print(f"  - {name}")
    if not removed:
        print("Все файлы на месте — чистить нечего.")


if __name__ == "__main__":
    asyncio.run(main())
