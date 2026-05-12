"""Skill: build_graph — граф связей между документами через общие сущности."""
from __future__ import annotations

from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.storage.sql_db import Document, DocumentRelation, Entity
import uuid


async def build_document_graph(db: AsyncSession) -> dict:
    """
    Строит граф документов:
    - Узлы: все не-superseded документы
    - Рёбра: shared_entity (общие нормализованные сущности), supersedes
    """
    # Загружаем документы
    docs_result = await db.execute(
        select(Document).where(Document.status != "superseded")
    )
    docs = list(docs_result.scalars().all())
    doc_ids = {d.id for d in docs}

    # Загружаем сущности
    entities_result = await db.execute(
        select(Entity).where(
            Entity.document_id.in_(doc_ids),
            Entity.normalized_name.isnot(None),
        )
    )
    entities = list(entities_result.scalars().all())

    # Строим map: normalized_name → list of document_ids
    name_to_docs: dict[str, list[str]] = defaultdict(list)
    for e in entities:
        if e.normalized_name and e.document_id:
            name_to_docs[e.normalized_name].append(e.document_id)

    # Находим пары документов со shared entities
    edge_weights: dict[tuple[str, str], int] = defaultdict(int)
    for doc_list in name_to_docs.values():
        unique_docs = list(set(doc_list))
        if len(unique_docs) < 2:
            continue
        for i in range(len(unique_docs)):
            for j in range(i + 1, len(unique_docs)):
                pair = tuple(sorted([unique_docs[i], unique_docs[j]]))
                edge_weights[pair] += 1  # type: ignore[index]

    # Рёбра supersedes
    supersedes_edges = []
    for d in docs:
        if d.superseded_by and d.superseded_by in doc_ids:
            supersedes_edges.append({"source": d.id, "target": d.superseded_by, "type": "supersedes"})

    # Сохраняем новые рёбра shared_entity в DocumentRelation (только сильные связи)
    await _upsert_relations(db, edge_weights, threshold=2)

    nodes = [
        {
            "id": d.id,
            "title": d.title,
            "status": d.status,
            "hierarchy_level": d.hierarchy_level,
            "type": d.type,
            "is_anchor": d.is_anchor,
        }
        for d in docs
    ]

    edges = [
        {
            "source": str(pair[0]),
            "target": str(pair[1]),
            "type": "shared_entity",
            "weight": weight,
        }
        for pair, weight in edge_weights.items()
        if weight >= 1
    ] + supersedes_edges

    return {"nodes": nodes, "edges": edges}


async def _upsert_relations(
    db: AsyncSession,
    edge_weights: dict[tuple[str, str], int],
    threshold: int = 2,
) -> None:
    """Записывает сильные связи (weight >= threshold) в document_relations."""
    existing_result = await db.execute(
        select(DocumentRelation).where(DocumentRelation.relation_type == "shared_entity")
    )
    existing = {
        (r.source_id, r.target_id): r
        for r in existing_result.scalars().all()
    }

    for (src, tgt), weight in edge_weights.items():
        if weight < threshold:
            continue
        key = (src, tgt)
        confidence = min(1.0, weight / 10.0)
        if key in existing:
            existing[key].confidence = confidence
        else:
            db.add(DocumentRelation(
                id=str(uuid.uuid4()),
                source_id=src,
                target_id=tgt,
                relation_type="shared_entity",
                confidence=confidence,
            ))

    await db.commit()
