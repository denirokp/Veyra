"""Skill: find_gaps — темы из корпуса, отсутствующие в текущей стратегии."""
from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients import get_llm
from app.settings import settings
from app.storage.sql_db import Chunk, Document

EXTRACT_TOPICS_PROMPT = """\
Извлеки 5-15 ключевых тем и направлений из текста.

Верни JSON массив строк. Темы — короткие (2-5 слов), конкретные.
Примеры: "агентский кабинет", "онбординг продавцов", "конверсия в листинг".

Только JSON массив, без markdown.\
"""

GAP_ANALYSIS_PROMPT = """\
Тебе даны два списка тем:
1. КОРПУС — все темы из всех документов команды
2. СТРАТЕГИЯ — темы из документов текущей стратегии

Найди темы из КОРПУСА которых НЕТ в СТРАТЕГИИ.
Это "серые зоны" — направления которые изучали, но не взяли в стратегию.

Верни JSON массив объектов:
{
  "topic": "название темы",
  "reason": "почему это может быть важно (1 предложение)",
  "priority": "high" | "medium" | "low"
}

Приоритет high — если тема упоминается в 3+ документах или связана с ростом/деньгами.
Только JSON массив, без markdown.\
"""


async def _extract_topics_from_chunks(chunks: list[str]) -> list[str]:
    if not chunks:
        return []
    combined = "\n\n---\n\n".join(chunks[:20])[:6000]
    llm = get_llm()
    response = await llm.messages.create(
        model=settings.LLM_MODEL,
        max_tokens=1024,
        system=EXTRACT_TOPICS_PROMPT,
        messages=[{"role": "user", "content": combined}],
    )
    raw = response.content[0].text.strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return []


async def find_gaps(db: AsyncSession) -> list[dict]:
    """
    Алгоритм:
    1. Получить тексты всех actual документов
    2. Получить тексты стратегических actual документов
    3. Извлечь темы через LLM
    4. Найти разрыв через LLM
    """
    # Все actual документы
    all_chunks_result = await db.execute(
        select(Chunk.content, Document.type, Document.status)
        .join(Document, Chunk.document_id == Document.id)
        .where(Document.status == "actual")
        .order_by(Chunk.chunk_index)
        .limit(100)
    )
    all_rows = all_chunks_result.fetchall()

    # Стратегические документы
    strategy_chunks_result = await db.execute(
        select(Chunk.content)
        .join(Document, Chunk.document_id == Document.id)
        .where(Document.status == "actual", Document.type == "strategy")
        .order_by(Chunk.chunk_index)
        .limit(40)
    )
    strategy_rows = strategy_chunks_result.fetchall()

    if not all_rows:
        return []

    all_topics = await _extract_topics_from_chunks([r[0] for r in all_rows])
    strategy_topics = await _extract_topics_from_chunks([r[0] for r in strategy_rows])

    if not all_topics:
        return []

    llm = get_llm()
    user_content = (
        f"КОРПУС (все темы):\n{json.dumps(all_topics, ensure_ascii=False)}\n\n"
        f"СТРАТЕГИЯ (темы из стратегических документов):\n"
        f"{json.dumps(strategy_topics, ensure_ascii=False)}"
    )
    response = await llm.messages.create(
        model=settings.LLM_MODEL,
        max_tokens=2048,
        system=GAP_ANALYSIS_PROMPT,
        messages=[{"role": "user", "content": user_content}],
    )
    raw = response.content[0].text.strip()
    try:
        gaps = json.loads(raw)
        # Сортируем: high → medium → low
        priority_order = {"high": 0, "medium": 1, "low": 2}
        return sorted(gaps, key=lambda g: priority_order.get(g.get("priority", "low"), 2))
    except json.JSONDecodeError:
        return []
