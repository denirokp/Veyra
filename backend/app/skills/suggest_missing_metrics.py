"""Skill: suggest_missing_metrics — предлагает недостающие KPI для инициативы/документа."""
from __future__ import annotations

import json

from sqlalchemy.ext.asyncio import AsyncSession

from app.clients import get_llm
from app.settings import settings
from app.storage.sql_db import search_entities_by_query

SYSTEM_PROMPT = """\
Ты аналитик KPI. Ты получаешь описание инициативы или документа и список метрик,
которые уже упоминаются в документах для похожих тем.

Предложи метрики, которых НЕ хватает для полноценного измерения успеха инициативы.

Верни JSON массив объектов:
[
  {
    "metric_name": "Название метрики",
    "why_needed": "Зачем эта метрика нужна для данной инициативы",
    "suggested_target": "Примерное целевое значение если можно предположить",
    "priority": "must_have|nice_to_have"
  }
]

ПРАВИЛА:
- Предлагай только релевантные, измеримые метрики
- must_have: без этой метрики нельзя судить об успехе
- nice_to_have: дополнительный контекст
- Не предлагай метрики если они уже есть в provided_metrics
- 3-7 рекомендаций, не больше
- Только JSON, без markdown\
"""


async def suggest_missing_metrics(
    title: str,
    text: str,
    db: AsyncSession,
) -> list[dict]:
    """Предлагает недостающие KPI на основе метрик из документов и LLM."""
    keywords = [w for w in (title + " " + text[:200]).lower().split() if len(w) > 3][:8]
    existing_entities = await search_entities_by_query(db, keywords, limit=20)

    existing_metrics = [
        f"{e.name} = {e.value} {e.unit or ''}".strip()
        for e in existing_entities
        if e.type == "metric"
    ]

    user_msg = (
        f"Инициатива: {title}\n\n"
        f"Описание: {text[:1000]}\n\n"
        + (
            f"Метрики уже упомянутые в документах:\n" + "\n".join(f"- {m}" for m in existing_metrics)
            if existing_metrics
            else "Метрики в документах не найдены."
        )
    )

    llm = get_llm()
    response = await llm.messages.create(
        model=settings.LLM_MODEL,
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_msg}],
    )

    raw = response.content[0].text.strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return []
