"""Query Planner — для составных запросов разбивает на под-вопросы.

Полноценный ReAct-агент с tool-calls — это overkill для текущего масштаба.
Здесь упрощённый planner: один LLM-вызов разбивает сложный запрос на
2-4 под-вопроса, retrieve() прогоняется для каждого, результаты потом
синтезируются основным агентом. Это сильно расширяет покрытие в составных
запросах вида "сначала X, потом Y, затем дай рекомендацию".
"""
from __future__ import annotations

import json
import logging
import re

from app.clients import call_llm

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = """\
Ты — планировщик ресёрча. На входе пользовательский запрос.

Если запрос:
- состоит из одного простого вопроса, или
- спрашивает один конкретный факт, или
- просит сделать X (один тип задачи)
→ верни {"plan": [], "rationale": "simple"}

Если запрос:
- содержит несколько разных тем/вопросов (через «и», «а также», «затем»)
- сначала требует анализ X, потом Y, потом синтез
- комбинирует «найди A» + «проверь B» + «напиши план C»
→ разбей его на 2-4 САМОСТОЯТЕЛЬНЫХ под-вопроса для retrieval. Каждый
под-вопрос — формулировка с ключевыми словами для поиска. Последний
под-вопрос обычно про синтез/рекомендации.

Формат СТРОГО JSON:
{
  "plan": ["под-вопрос 1", "под-вопрос 2", ...],
  "rationale": "одно предложение почему такая декомпозиция"
}

Без markdown, без объяснений вокруг JSON.\
"""


async def decompose(query: str, max_subqueries: int = 4) -> list[str]:
    """Возвращает список под-запросов или [] если запрос простой/неразложимый."""
    try:
        raw = await call_llm(
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": query}],
            max_tokens=400,
        )
    except Exception as exc:
        logger.warning("query_planner.decompose failed: %s", exc)
        return []

    parsed = None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if m:
            try:
                parsed = json.loads(m.group())
            except json.JSONDecodeError:
                pass
    if not isinstance(parsed, dict):
        return []
    plan = parsed.get("plan", []) or []
    if not isinstance(plan, list):
        return []
    cleaned = [str(p).strip() for p in plan if str(p).strip()][:max_subqueries]
    if cleaned:
        logger.info("query_planner: decomposed into %d sub-queries (%s)",
                    len(cleaned), parsed.get("rationale", ""))
    return cleaned
