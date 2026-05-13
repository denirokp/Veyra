"""Skill: find_contradictions — поиск числовых расхождений между документами.

Улучшения:
- _same_period: понимает год, месяц, квартал. «Q1 2025» vs «Q3 2025» → разные периоды.
- Поиск по сущностям: fuzzy match имён метрик через difflib (0.85 threshold).
"""
from __future__ import annotations

import logging
import re
import uuid
from difflib import SequenceMatcher

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.storage.sql_db import Entity, save_contradiction

logger = logging.getLogger(__name__)

FUZZY_THRESHOLD = 0.85  # similarity ratio для имён метрик


# ── Сравнение значений ────────────────────────────────────────────────────────

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
        return diff > 0.05
    except (ValueError, TypeError):
        return str(val_a).strip().lower() != str(val_b).strip().lower()


# ── Парсер периодов ──────────────────────────────────────────────────────────

_QUARTER_RE = re.compile(r"q\s*([1-4])\s*[/\-' ]?\s*(\d{2,4})|(\d{2,4})\s*[/\-' ]?\s*q\s*([1-4])", re.IGNORECASE)
_MONTH_RU = {
    "январ": 1, "феврал": 2, "март": 3, "апрел": 4, "ма": 5, "июн": 6,
    "июл": 7, "август": 8, "сентябр": 9, "октябр": 10, "ноябр": 11, "декабр": 12,
}


def _parse_period(value: str | None) -> tuple[int | None, int | None, int | None]:
    """
    Возвращает (year, quarter, month). Любое поле может быть None.
    Поддерживает: '2025', '2025-03', '2025-03-15', 'Q1 2025', '2025 Q1',
    'март 2025', 'март 2025г'.
    """
    if not value:
        return (None, None, None)
    s = str(value).strip().lower()

    # ISO YYYY-MM-DD / YYYY-MM
    m = re.match(r"^(\d{4})(?:[-/](\d{1,2})(?:[-/](\d{1,2}))?)?$", s)
    if m:
        year = int(m.group(1))
        month = int(m.group(2)) if m.group(2) else None
        quarter = (month - 1) // 3 + 1 if month else None
        return (year, quarter, month)

    # Q1 2025 / 2025 Q1 / Q1'25
    m = _QUARTER_RE.search(s)
    if m:
        q = int(m.group(1) or m.group(4))
        y = int(m.group(2) or m.group(3))
        if y < 100:
            y += 2000
        return (y, q, None)

    # «март 2025», «марта 2025г»
    year_match = re.search(r"(\d{4})", s)
    year = int(year_match.group(1)) if year_match else None
    for prefix, month in _MONTH_RU.items():
        if prefix in s:
            quarter = (month - 1) // 3 + 1
            return (year, quarter, month)

    # Только год
    if year:
        return (year, None, None)
    return (None, None, None)


def _same_period(date_a: str | None, date_b: str | None) -> bool:
    """
    True если периоды совместимы (одинаковые) или один из них неизвестен.
    Раньше сравнивался только год → 'Q1 2025' и 'Q4 2025' считались одним периодом.
    """
    if not date_a and not date_b:
        return True
    if not date_a or not date_b:
        return True  # один без даты — не исключаем

    ya, qa, ma = _parse_period(date_a)
    yb, qb, mb = _parse_period(date_b)

    if ya is None or yb is None:
        return True

    if ya != yb:
        return False

    # Если у обоих есть месяц — сравниваем месяцы
    if ma is not None and mb is not None:
        return ma == mb
    # Если у обоих есть квартал — сравниваем кварталы
    if qa is not None and qb is not None:
        return qa == qb
    # Один с гранулярностью «год», другой точнее — считаем совместимыми
    return True


# ── Fuzzy-матчинг имён метрик ────────────────────────────────────────────────

def _normalize_for_match(name: str) -> str:
    """Lowercase, без пунктуации, схлопывает пробелы."""
    s = re.sub(r"[^\w\s]+", " ", name.lower(), flags=re.UNICODE)
    return " ".join(s.split())


def _similar(a: str, b: str) -> float:
    return SequenceMatcher(None, _normalize_for_match(a), _normalize_for_match(b)).ratio()


async def _find_matching_metrics(
    db: AsyncSession,
    normalized_name: str,
    exclude_document_id: str,
) -> list[Entity]:
    """
    Сначала пробуем точный матч (быстро, индекс).
    Если ничего — fuzzy-матч среди всех метрик (medlennее, но full scan через ilike).
    """
    # Точное совпадение
    result = await db.execute(
        select(Entity).where(
            Entity.type == "metric",
            Entity.normalized_name == normalized_name,
            Entity.document_id != exclude_document_id,
        )
    )
    exact = list(result.scalars().all())
    if exact:
        return exact

    # Fuzzy — берём кандидатов по первому слову (грубый префильтр)
    first_word = normalized_name.split()[0] if normalized_name else ""
    if not first_word or len(first_word) < 3:
        return []

    result = await db.execute(
        select(Entity).where(
            Entity.type == "metric",
            Entity.normalized_name.ilike(f"%{first_word}%"),
            Entity.document_id != exclude_document_id,
        )
    )
    candidates = list(result.scalars().all())
    matched = [c for c in candidates if _similar(c.normalized_name or "", normalized_name) >= FUZZY_THRESHOLD]
    if matched and not exact:
        logger.debug("fuzzy-match: %r → %d кандидатов", normalized_name, len(matched))
    return matched


async def check_and_save_contradictions(
    new_metrics: list[dict],
    new_document_id: str,
    db: AsyncSession,
) -> list[dict]:
    """
    Сравниваем новые метрики с существующими в entity_memory.
    При конфликте по совместимому периоду и существенному отклонению — пишем в contradictions.
    """
    found: list[dict] = []

    for metric in new_metrics:
        normalized = metric.get("normalized_name", "")
        if not normalized:
            continue

        existing = await _find_matching_metrics(db, normalized, new_document_id)

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
                "period": metric.get("date_context"),
                "status": "open",
            }
            await save_contradiction(db, contradiction)
            found.append(contradiction)

    return found
