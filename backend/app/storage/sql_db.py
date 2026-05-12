"""SQLite schema — v4.0: numeric_contradictions, logic_signals, updated entity types."""
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


class NumericContradiction(Base):
    __tablename__ = "numeric_contradictions"

    id = Column(String, primary_key=True)
    metric = Column(Text, nullable=False)
    value_a = Column(Text)
    value_b = Column(Text)
    document_id_a = Column(String, ForeignKey("documents.id"))
    document_id_b = Column(String, ForeignKey("documents.id"))
    period = Column(Text)
    status = Column(String, default="open")  # open | resolved | dismissed
    resolved_by = Column(String, ForeignKey("documents.id"), nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    resolved_at = Column(DateTime)


# Backward-compat alias — код написанный с Contradiction продолжает работать
Contradiction = NumericContradiction


class LogicSignal(Base):
    __tablename__ = "logic_signals"

    id = Column(String, primary_key=True)
    signal_type = Column(String)  # strategic | operational | priority | client
    statement_a = Column(Text)
    statement_b = Column(Text)
    document_id_a = Column(String, ForeignKey("documents.id"))
    document_id_b = Column(String, ForeignKey("documents.id"))
    status = Column(String, default="open")  # open | reviewed | dismissed
    review_notes = Column(Text)
    confidence = Column(Float)
    created_at = Column(DateTime, server_default=func.now())


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


def compute_hierarchy_level(
    status: str,
    is_anchor: bool,
    doc_type: str | None,
) -> int:
    """L1–L6 по правилам из ТЗ."""
    if is_anchor:
        return 1
    if status == "superseded":
        return 7  # исключён из ответов
    if status == "actual":
        if doc_type == "strategy":
            return 2
        if doc_type in ("research", "plan"):
            return 3
        if doc_type == "operational":
            return 4
        return 3
    if status in ("draft", "unknown"):
        return 5
    if status == "archived":
        return 6
    return 5


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_session() -> AsyncSession:
    async with AsyncSession(engine) as session:
        yield session


# ── Document CRUD ────────────────────────────────────────────────────────────

async def create_document(session: AsyncSession, data: dict) -> Document:
    data["hierarchy_level"] = compute_hierarchy_level(
        data.get("status", "unknown"),
        data.get("is_anchor", False),
        data.get("type"),
    )
    doc = Document(**data)
    session.add(doc)
    await session.commit()
    await session.refresh(doc)
    return doc


async def get_document(session: AsyncSession, doc_id: str) -> Document | None:
    from sqlalchemy import select
    result = await session.execute(select(Document).where(Document.id == doc_id))
    return result.scalar_one_or_none()


async def list_documents(
    session: AsyncSession,
    status: str | None = None,
    segment: str | None = None,
) -> list[Document]:
    from sqlalchemy import select
    q = select(Document).where(Document.status != "superseded")
    if status:
        q = q.where(Document.status == status)
    if segment:
        q = q.where(Document.segment == segment)
    q = q.order_by(Document.hierarchy_level, Document.created_at.desc())
    result = await session.execute(q)
    return list(result.scalars().all())


async def update_document(session: AsyncSession, doc_id: str, patch: dict) -> Document | None:
    doc = await get_document(session, doc_id)
    if doc is None:
        return None
    for k, v in patch.items():
        setattr(doc, k, v)
    doc.hierarchy_level = compute_hierarchy_level(
        doc.status, doc.is_anchor, doc.type
    )
    await session.commit()
    await session.refresh(doc)
    return doc


async def save_chunks(session: AsyncSession, chunks: list[dict]) -> None:
    from sqlalchemy.dialects.sqlite import insert as sqlite_insert
    if not chunks:
        return
    await session.execute(Chunk.__table__.insert(), chunks)
    await session.commit()


# ── Entity CRUD ──────────────────────────────────────────────────────────────

async def save_entities(session: AsyncSession, entities: list[dict]) -> None:
    if not entities:
        return
    await session.execute(Entity.__table__.insert(), entities)
    await session.commit()


async def search_entities_by_query(
    session: AsyncSession,
    keywords: list[str],
    limit: int = 20,
) -> list[Entity]:
    """Поиск сущностей по ключевым словам из запроса для обогащения контекста."""
    from sqlalchemy import select, or_
    if not keywords:
        return []
    conditions = [
        Entity.normalized_name.ilike(f"%{kw.lower()}%")
        for kw in keywords[:8]
    ]
    q = (
        select(Entity)
        .where(or_(*conditions))
        .order_by(Entity.confidence.desc())
        .limit(limit)
    )
    result = await session.execute(q)
    return list(result.scalars().all())


async def get_open_contradictions_for_docs(
    session: AsyncSession,
    document_ids: list[str],
) -> list[Contradiction]:
    """Возвращает открытые расхождения для набора документов."""
    from sqlalchemy import select, or_
    if not document_ids:
        return []
    q = select(Contradiction).where(
        Contradiction.status == "open",
        or_(
            Contradiction.document_id_a.in_(document_ids),
            Contradiction.document_id_b.in_(document_ids),
        ),
    )
    result = await session.execute(q)
    return list(result.scalars().all())


async def mark_overdue_promises(session: AsyncSession) -> int:
    """При старте помечает просроченные open-обещания как overdue."""
    from sqlalchemy import select, update
    from datetime import date
    today = date.today()
    result = await session.execute(
        update(Promise)
        .where(Promise.status == "open", Promise.deadline < today)
        .values(status="overdue")
        .returning(Promise.id)
    )
    await session.commit()
    rows = result.fetchall()
    return len(rows)


async def get_entities_for_metric(
    session: AsyncSession,
    metric_name: str,
    doc_id: str | None = None,
) -> list[Entity]:
    from sqlalchemy import select, or_
    q = select(Entity).where(
        Entity.type == "metric",
        Entity.normalized_name == metric_name,
    )
    if doc_id:
        q = q.where(Entity.document_id != doc_id)
    result = await session.execute(q)
    return list(result.scalars().all())


# ── Contradiction CRUD ────────────────────────────────────────────────────────

async def save_contradiction(session: AsyncSession, data: dict) -> Contradiction:
    c = Contradiction(**data)
    session.add(c)
    await session.commit()
    return c


async def list_contradictions(
    session: AsyncSession, status: str | None = None
) -> list[Contradiction]:
    from sqlalchemy import select
    q = select(Contradiction)
    if status:
        q = q.where(Contradiction.status == status)
    q = q.order_by(Contradiction.created_at.desc())
    result = await session.execute(q)
    return list(result.scalars().all())


# ── Logic Signals CRUD ───────────────────────────────────────────────────────

async def save_logic_signal(session: AsyncSession, data: dict) -> LogicSignal:
    s = LogicSignal(**data)
    session.add(s)
    await session.commit()
    return s


async def save_logic_signals(session: AsyncSession, signals: list[dict]) -> None:
    if not signals:
        return
    for s in signals:
        session.add(LogicSignal(**s))
    await session.commit()


async def list_logic_signals(
    session: AsyncSession, status: str | None = None
) -> list[LogicSignal]:
    from sqlalchemy import select
    q = select(LogicSignal)
    if status:
        q = q.where(LogicSignal.status == status)
    q = q.order_by(LogicSignal.confidence.desc().nullslast(), LogicSignal.created_at.desc())
    result = await session.execute(q)
    return list(result.scalars().all())


async def get_open_logic_signals_for_docs(
    session: AsyncSession,
    document_ids: list[str],
) -> list[LogicSignal]:
    from sqlalchemy import select, or_
    if not document_ids:
        return []
    q = select(LogicSignal).where(
        LogicSignal.status == "open",
        or_(
            LogicSignal.document_id_a.in_(document_ids),
            LogicSignal.document_id_b.in_(document_ids),
        ),
    )
    result = await session.execute(q)
    return list(result.scalars().all())


# ── Promise CRUD ──────────────────────────────────────────────────────────────

async def save_promises(session: AsyncSession, promises: list[dict]) -> None:
    if not promises:
        return
    await session.execute(Promise.__table__.insert(), promises)
    await session.commit()


async def list_promises(
    session: AsyncSession, status: str | None = None
) -> list[Promise]:
    from sqlalchemy import select
    q = select(Promise)
    if status:
        q = q.where(Promise.status == status)
    q = q.order_by(Promise.deadline.asc().nullslast())
    result = await session.execute(q)
    return list(result.scalars().all())
