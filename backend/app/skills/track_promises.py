"""Skill: track_promises — извлечение обещаний и планов из документа."""
from __future__ import annotations

import json
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.clients import get_llm
from app.settings import settings
from app.storage.sql_db import save_promises

SYSTEM_PROMPT = """\
Ты аналитик планов и обещаний. Найди в тексте все обещания, планы, намерения команды.

Типы:
1. explicit_numeric — явное с числом: «рост конверсии на 25% к Q4 2025»
2. explicit_verbal — явное без числа: «запустим агентский кабинет в Q3»
3. implicit — неявное: «планируем рассмотреть», «в следующем квартале изучим»

Верни строго валидный JSON массив. Каждый элемент:
{
  "text": "точная цитата из текста",
  "normalized_text": "нормализованная формулировка обещания",
  "deadline": "YYYY-MM-DD или YYYY-MM или YYYY или null",
  "metric": "числовая цель если есть, иначе null",
  "target_value": число или null,
  "promise_type": "explicit_numeric" | "explicit_verbal" | "implicit"
}

Правила:
- Только то что явно в тексте — никаких интерпретаций
- Для неявных: только если есть слова «планируем», «будем», «рассмотрим», «в следующем»
- Пустой массив если нет обещаний

Ответь ТОЛЬКО JSON массивом, без markdown.\
"""


async def extract_promises_from_text(
    text: str,
    document_date: str | None = None,
) -> list[dict]:
    llm = get_llm()
    user_content = text[:8000]
    if document_date:
        user_content = f"Дата документа: {document_date}\n\n{user_content}"

    response = await llm.messages.create(
        model=settings.LLM_MODEL,
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_content}],
    )
    raw = response.content[0].text.strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        import re
        match = re.search(r"\[.*\]", raw, re.DOTALL)
        if match:
            return json.loads(match.group())
        return []


async def extract_and_save_promises(
    text: str,
    document_id: str,
    document_metadata: dict,
    db: AsyncSession,
) -> list[dict]:
    document_date = str(document_metadata.get("created_at") or "")
    promises = await extract_promises_from_text(text, document_date or None)

    rows = []
    for p in promises:
        if not isinstance(p, dict) or not p.get("text"):
            continue
        rows.append({
            "id": str(uuid.uuid4()),
            "text": p["text"],
            "normalized_text": p.get("normalized_text", p["text"]),
            "document_id": document_id,
            "document_date": document_metadata.get("created_at"),
            "deadline": p.get("deadline"),
            "metric": p.get("metric"),
            "target_value": p.get("target_value"),
            "status": "open",
        })

    await save_promises(db, rows)
    return rows
