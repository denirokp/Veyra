from uuid import UUID

from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.schemas import DocumentOut, DocumentPatch
from app.storage.sql_db import get_session

router = APIRouter(tags=["documents"])


@router.post("/documents", response_model=DocumentOut)
async def upload_document(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_session),
):
    # TODO: парсинг → chunking → индексация → extract_entities → skills
    raise NotImplementedError


@router.get("/documents", response_model=list[DocumentOut])
async def list_documents(db: AsyncSession = Depends(get_session)):
    # TODO: SELECT с фильтрами
    raise NotImplementedError


@router.patch("/documents/{doc_id}", response_model=DocumentOut)
async def patch_document(
    doc_id: UUID,
    patch: DocumentPatch,
    db: AsyncSession = Depends(get_session),
):
    # TODO: обновление статуса / якоря / стиля + пересчёт hierarchy_level
    raise NotImplementedError


@router.delete("/documents/{doc_id}")
async def delete_document(doc_id: UUID, db: AsyncSession = Depends(get_session)):
    # TODO: удаление из ChromaDB + SQLite
    raise NotImplementedError
