"""Skill: market_agent_lite — рыночный контекст на основе знаний LLM."""
from __future__ import annotations

import json
import logging

from app.clients import call_llm

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
Ты аналитик рынка. Используй свои знания о рынке, конкурентах и трендах
для предоставления контекста по заданной теме.

ВАЖНО: ты используешь знания из обучения, а НЕ данные компании.
Все ответы — гипотезы, требующие верификации.

Верни JSON:
{
  "market_trends": ["Тренд 1", "Тренд 2"],
  "competitors": [
    {"name": "Компания", "approach": "Что они делают по этой теме"}
  ],
  "benchmarks": ["Отраслевой бенчмарк или метрика"],
  "risks": ["Рыночный риск специфичный для этой инициативы"],
  "summary": "2-3 предложения: рыночный контекст для инициативы"
}

Если тема слишком специфична и данных нет — честно напиши "Нет данных" в summary.
Только JSON, без markdown.\
"""


async def get_market_context(topic: str, segment: str | None = None) -> dict:
    """LLM-based market context. Использует знания модели, помечено как гипотеза."""
    prompt = f"Тема инициативы: {topic}"
    if segment:
        prompt += f"\nСегмент: {segment}"

    try:
        raw = await call_llm(
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=800,
        )
    except Exception as e:
        logger.error("market_agent: LLM call failed: %s", e)
        return {
            "summary": "Нет данных",
            "_source": "llm_knowledge",
            "_disclaimer": "LLM-вызов не удался.",
        }

    try:
        data = json.loads(raw)
        data["_source"] = "llm_knowledge"
        data["_disclaimer"] = "Гипотеза модели на основе обучающих данных. Требует верификации."
        return data
    except json.JSONDecodeError as e:
        logger.warning("market_agent: невалидный JSON: %s | head=%r", e, raw[:200])
        return {
            "summary": "Нет данных",
            "_source": "llm_knowledge",
            "_disclaimer": "Не удалось распарсить ответ LLM.",
        }
