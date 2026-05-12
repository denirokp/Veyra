"""SQLite schema — documents, chunks, entities, contradictions, promises, graph, style_feedback."""
from sqlalchemy import (
    Boolean, Column, Date, DateTime, Float, ForeignKey,
    Integer, String, Text, func,
)
from sqlalchemy.dialects.sqlite import JSON
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import DeclarativeBase, relationship

from app.settings import settings

engine = create_async_engine(settings.DATABASE_URL, echo=False)


class Base(DeclarativeBase):
    pass


class Document(Base):
    __tablename__ = "documents"

    id = Column(String, primary_key=True)
    title = Column(Text, nullable=False)
    type = Column(String)
    segment = Column(String)
    author = Column(String)
    created_at = Column(Date)
    updated_at = Column(Date)
    status = Column(String, default="unknown")
    superseded_by = Column(String, ForeignKey("documents.id"), nullable=True)
    is_anchor = Column(Boolean, default=False)
    is_style_anchor = Column(Boolean, default=False)
    hierarchy_level = Column(Integer)
    confluence_url = Column(Text)
    file_path = Column(Text)
    chunk_count = Column(Integer)
    indexed_at = Column(DateTime, server_default=func.now())

    chunks = relationship("Chunk", back_populates="document")


class Chunk(Base):
    __tablename__ = "chunks"

    id = Column(String, primary_key=True)
    document_id = Column(String, ForeignKey("documents.id"), nullable=False)
    content = Column(Text, nullable=False)
    section = Column(Text)
    subsection = Column(Text)
    chunk_index = Column(Integer)
    token_count = Column(Integer)
    embedding_id = Column(String)
    metadata_ = Column("metadata", JSON)

    document = relationship("Document", back_populates="chunks")


class Entity(Base):
    __tablename__ = "entities"

    id = Column(String, primary_key=True)
    type = Column(String)
    name = Column(Text, nullable=False)
    normalized_name = Column(Text)
    value = Column(Text)
    unit = Column(Text)
    date_context = Column(Date)
    document_id = Column(String, ForeignKey("documents.id"))
    chunk_id = Column(String, ForeignKey("chunks.id"))
    confidence = Column(Float)
    created_at = Column(DateTime, server_default=func.now())


class Contradiction(Base):
    __tablename__ = "contradictions"

    id = Column(String, primary_key=True)
    metric = Column(Text, nullable=False)
    value_a = Column(Text)
    value_b = Column(Text)
    document_id_a = Column(String, ForeignKey("documents.id"))
    document_id_b = Column(String, ForeignKey("documents.id"))
    status = Column(String, default="open")
    resolved_by = Column(String)
    created_at = Column(DateTime, server_default=func.now())
    resolved_at = Column(DateTime)


class Promise(Base):
    __tablename__ = "promises"

    id = Column(String, primary_key=True)
    text = Column(Text, nullable=False)
    normalized_text = Column(Text)
    document_id = Column(String, ForeignKey("documents.id"))
    document_date = Column(Date)
    deadline = Column(Date)
    metric = Column(Text)
    target_value = Column(Float)
    status = Column(String, default="open")
    resolved_at = Column(Date)
    notes = Column(Text)


class DocumentRelation(Base):
    __tablename__ = "document_relations"

    id = Column(String, primary_key=True)
    source_id = Column(String, ForeignKey("documents.id"))
    target_id = Column(String, ForeignKey("documents.id"))
    relation_type = Column(String)
    confidence = Column(Float)
    created_at = Column(DateTime, server_default=func.now())


class StyleFeedback(Base):
    __tablename__ = "style_feedback"

    id = Column(String, primary_key=True)
    document_id = Column(String)
    original_text = Column(Text)
    edited_text = Column(Text)
    diff = Column(JSON)
    created_at = Column(DateTime, server_default=func.now())
    applied = Column(Boolean, default=False)


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_session() -> AsyncSession:
    async with AsyncSession(engine) as session:
        yield session
