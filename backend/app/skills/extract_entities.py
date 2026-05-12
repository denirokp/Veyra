"""Skill: extract_entities — извлечение сущностей из документа через LLM."""
from __future__ import annotations

import json
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.clients import get_llm
from app.settings import settings
from app.storage.sql_db import save_entities
from app.skills.find_contradictions import check_and_save_contradictions

SYSTEM_PROMPT = """\
Ты аналитик данных. Извлеки из текста все структурированные сущности.

Верни строго валидный JSON массив объектов. Каждый объект — одна сущность.

Типы сущностей:
- "metric": числовая метрика (name, value, unit, date_context, normalized_name)
- "promise": обещание/план (name, deadline, normalized_name)
- "person": человек (name, normalized_name)
- "project": проект/инициатива (name, normalized_name)
- "decision": решение (name, normalized_name)

Поля объекта:
{
  "type": "metric" | "promise" | "person" | "project" | "decision",
  "name": "оригинальное название из текста",
  "normalized_name": "нормализованное (lowercase, без пунктуации)",
  "value": "числовое значение или null",
  "unit": "единица измерения или null",
  "date_context": "YYYY-MM-DD или YYYY-MM или YYYY или null",
  "confidence": 0.0-1.0
}

Правила:
- Только то что явно есть в тексте
- Для метрик: не пропускай единицы (%, руб, шт, %)
- Для дат: нормализуй к ISO формату
- Если не уверен — снижай confidence
- Пустой массив если нет сущностей

Ответь ТОЛЬКО JSON массивом, без markdown обёртки.\
"""


async def extract_entities_from_text(text: str) -> list[dict]:
    llm = get_llm()
    response = await llm.messages.create(
        model=settings.LLM_MODEL,
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": text[:8000]}],  # обрезаем длинные тексты
    )
    raw = response.content[0].text.strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # Попытка вытащить JSON из текста
        import re
        match = re.search(r"\[.*\]", raw, re.DOTALL)
        if match:
            return json.loads(match.group())
        return []


async def extract_and_save(
    text: str,
    document_id: str,
    document_metadata: dict,
    db: AsyncSession,
) -> list[dict]:
    entities = await extract_entities_from_text(text)

    rows = []
    for e in entities:
        if not isinstance(e, dict) or not e.get("name"):
            continue
        rows.append({
            "id": str(uuid.uuid4()),
            "type": e.get("type", "other"),
            "name": e["name"],
            "normalized_name": e.get("normalized_name", e["name"].lower()),
            "value": e.get("value"),
            "unit": e.get("unit"),
            "date_context": e.get("date_context"),
            "document_id": document_id,
            "chunk_id": None,
            "confidence": e.get("confidence", 0.8),
        })

    await save_entities(db, rows)

    # Проверяем числовые расхождения с уже существующими метриками
    metrics = [r for r in rows if r["type"] == "metric"]
    if metrics:
        await check_and_save_contradictions(metrics, document_id, db)

    return rows
