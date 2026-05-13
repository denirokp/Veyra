"""Skill: initiative_review — 7-блочный разбор инициативы через документы команды."""
from __future__ import annotations

import asyncio
import json
import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.clients import call_llm
from app.rag.retriever import retrieve
from app.skills.market_agent import get_market_context
from app.storage.sql_db import (
    get_open_contradictions_for_docs,
    get_open_logic_signals_for_docs,
    search_entities_by_query,
)

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
Ты аналитик корпоративной памяти. Ты получаешь текст инициативы и релевантный контекст
из документов компании. Твоя задача — дать 7-блочный структурированный разбор.

Верни JSON строго с этими ключами:
{
  "summary": "1-2 предложения: суть инициативы своими словами",
  "strategic_anchors": [
    {
      "title": "Название документа из документов",
      "relevance": "Почему этот документ релевантен инициативе",
      "alignment": "supports|neutral|conflicts"
    }
  ],
  "conflicts": [
    {
      "description": "Описание: что именно из документов расходится с инициативой",
      "severity": "high|medium|low",
      "source": "Документ-источник"
    }
  ],
  "gaps": [
    {
      "gap_type": "metric|owner|deadline|resource|market_validation",
      "description": "Конкретно чего не хватает"
    }
  ],
  "analogues": [
    {
      "title": "Похожая инициатива или документ из документов",
      "outcome": "Чем закончилось / текущий статус",
      "lesson": "Вывод: что учесть"
    }
  ],
  "external_context": "Внешний рыночный контекст если известен из документов, иначе 'Нет данных'",
  "recommendation": {
    "verdict": "approve|needs_work|reject",
    "reasoning": "2-4 предложения с конкретным обоснованием"
  }
}

ПРАВИЛА:
- Ссылайся только на документы и факты из предоставленного контекста
- conflicts формулируй как "сигнал к проверке", не как окончательное противоречие
- gaps: будь конкретен — какие метрики успеха, чей owner, к какому дедлайну
- Если по какому-то блоку данных нет — оставь пустой массив [] или 'Нет данных'
- verdict: approve если явных блокеров нет; needs_work если есть важные gaps/conflicts; reject если противоречит стратегии
- Только JSON, без markdown\
"""


def _build_context(
    initiative_title: str,
    initiative_text: str,
    chunks: list,
    contradictions: list,
    logic_signals: list,
    entities: list,
) -> str:
    parts = [
        f"=== ИНИЦИАТИВА: {initiative_title} ===\n{initiative_text}\n",
    ]

    if chunks:
        parts.append("=== РЕЛЕВАНТНЫЕ ДОКУМЕНТЫ ===")
        seen_docs: set[str] = set()
        for c in chunks[:12]:
            doc_id = c.document_id
            label = f"[L{c.hierarchy_level} | {c.status}]"
            if doc_id not in seen_docs:
                seen_docs.add(doc_id)
                title = c.metadata.get("title", doc_id)
                parts.append(f"\n--- {title} {label} ---")
            parts.append(c.content[:800])

    if contradictions:
        parts.append("\n=== ОТКРЫТЫЕ ЧИСЛОВЫЕ РАСХОЖДЕНИЯ ===")
        for con in contradictions[:5]:
            parts.append(
                f"• {con.metric}: {con.value_a} vs {con.value_b}"
                + (f" (период: {con.period})" if con.period else "")
            )

    if logic_signals:
        parts.append("\n=== ЛОГИЧЕСКИЕ СИГНАЛЫ В ДОКУМЕНТАХ ===")
        for sig in logic_signals[:5]:
            parts.append(
                f"• [{sig.signal_type}] {sig.statement_a[:200]} | vs | {sig.statement_b[:200]}"
            )

    if entities:
        parts.append("\n=== КЛЮЧЕВЫЕ МЕТРИКИ ИЗ ПАМЯТИ ===")
        for e in entities[:10]:
            val_str = f" = {e.value} {e.unit or ''}".rstrip() if e.value else ""
            parts.append(f"• {e.name}{val_str}")

    return "\n".join(parts)


async def run_initiative_review(
    title: str,
    text: str,
    db: AsyncSession,
) -> dict:
    """
    Полный пайплайн initiative review:
    1. Hybrid RAG + Market Agent Lite (параллельно)
    2. Загрузка расхождений, сигналов, сущностей
    3. LLM-анализ → 7 блоков
    """
    query = f"{title}\n{text[:500]}"

    # Параллельно: RAG + Market Agent
    chunks, market_ctx = await asyncio.gather(
        retrieve(query, top_k=15, include_archive=True),
        get_market_context(title),
    )

    doc_ids = list({c.document_id for c in chunks})

    # Параллельно: расхождения + сигналы + сущности
    keywords = [w for w in title.lower().split() if len(w) > 3][:6]

    async def _empty() -> list:
        return []

    # AsyncSession не поддерживает параллельные запросы — выполняем последовательно
    contradictions = await (
        get_open_contradictions_for_docs(db, doc_ids) if doc_ids else _empty()
    )
    logic_signals = await (
        get_open_logic_signals_for_docs(db, doc_ids) if doc_ids else _empty()
    )
    entities = await (
        search_entities_by_query(db, keywords, limit=15) if keywords else _empty()
    )

    context = _build_context(title, text, chunks, contradictions, logic_signals, entities)

    # Добавляем рыночный контекст к промпту
    if market_ctx.get("summary") and market_ctx["summary"] != "Нет данных":
        market_lines = ["\n=== РЫНОЧНЫЙ КОНТЕКСТ (знания модели, гипотеза) ==="]
        market_lines.append(f"Резюме: {market_ctx['summary']}")
        if market_ctx.get("market_trends"):
            market_lines.append("Тренды: " + "; ".join(market_ctx["market_trends"][:3]))
        if market_ctx.get("competitors"):
            for c in market_ctx["competitors"][:3]:
                market_lines.append(f"• {c['name']}: {c['approach']}")
        context += "\n" + "\n".join(market_lines)

    try:
        raw = await call_llm(
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": context}],
            max_tokens=3000,
        )
    except Exception as e:
        logger.error("initiative_review: LLM call failed: %s", e)
        raw = ""

    try:
        result = json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        import re
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if match:
            try:
                result = json.loads(match.group())
            except json.JSONDecodeError as e:
                logger.warning("initiative_review: regex-fallback не распарсился: %s", e)
                result = {}
        else:
            logger.warning("initiative_review: невалидный JSON, head=%r", raw[:200])
            result = {}

    if not result:
        result = {
            "summary": "Не удалось разобрать ответ LLM",
            "strategic_anchors": [],
            "conflicts": [],
            "gaps": [],
            "analogues": [],
            "external_context": "Нет данных",
            "recommendation": {"verdict": "needs_work", "reasoning": raw[:500] or "LLM не ответил"},
        }

    return {
        **result,
        "market_context": market_ctx,
        "metadata": {
            "chunks_used": len(chunks),
            "doc_ids": doc_ids[:10],
            "contradictions_found": len(contradictions),
            "logic_signals_found": len(logic_signals),
        },
    }
