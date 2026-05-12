"""Skill: find_contradictions — поиск числовых расхождений между документами."""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.storage.sql_db import Entity, save_contradiction


def _values_conflict(val_a: str | None, val_b: str | None) -> bool:
    """Грубое сравнение числовых значений. True если расхождение > 5%."""
    if not val_a or not val_b:
        return False
    try:
        a = float(str(val_a).replace(",", ".").replace("%", "").strip())
        b = float(str(val_b).replace(",", ".").replace("%", "").strip())
        if a == 0 and b == 0:
            return False
        diff = abs(a - b) / (max(abs(a), abs(b)) or 1)
        return diff > 0.05  # расхождение более 5% — конфликт
    except (ValueError, TypeError):
        # Строковые значения — сравниваем напрямую
        return str(val_a).strip().lower() != str(val_b).strip().lower()


def _same_period(date_a: str | None, date_b: str | None) -> bool:
    """True если даты в пределах одного года (или обе пустые)."""
    if not date_a and not date_b:
        return True
    if not date_a or not date_b:
        return True  # без даты — не исключаем
    try:
        year_a = str(date_a)[:4]
        year_b = str(date_b)[:4]
        return year_a == year_b
    except Exception:
        return True


async def check_and_save_contradictions(
    new_metrics: list[dict],
    new_document_id: str,
    db: AsyncSession,
) -> list[dict]:
    """
    Сравниваем новые метрики с существующими в entity_memory.
    При конфликте — пишем в contradictions.
    """
    found: list[dict] = []

    for metric in new_metrics:
        normalized = metric.get("normalized_name", "")
        if not normalized:
            continue

        # Ищем ту же метрику в других документах
        result = await db.execute(
            select(Entity).where(
                Entity.type == "metric",
                Entity.normalized_name == normalized,
                Entity.document_id != new_document_id,
            )
        )
        existing: list[Entity] = list(result.scalars().all())

        for existing_entity in existing:
            if not _values_conflict(metric.get("value"), existing_entity.value):
                continue
            if not _same_period(metric.get("date_context"), str(existing_entity.date_context or "")):
                continue

            contradiction = {
                "id": str(uuid.uuid4()),
                "metric": metric["name"],
                "value_a": metric.get("value"),
                "value_b": existing_entity.value,
                "document_id_a": new_document_id,
                "document_id_b": existing_entity.document_id,
                "status": "open",
            }
            await save_contradiction(db, contradiction)
            found.append(contradiction)

    return found
