"""Skill: find_logic_signals — поиск стратегических/операционных конфликтов в подходах."""
from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from itertools import combinations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients import call_llm, parse_json_array
from app.storage.sql_db import Chunk, Document, save_logic_signals

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
Ты аналитик стратегических документов. Найди пары утверждений из РАЗНЫХ документов,
которые могут указывать на логический конфликт в подходах команды.

ТИПЫ СИГНАЛОВ:
- strategic: Один документ говорит "делаем A", другой "делаем NOT-A" по одной стратегической теме
- operational: Обещали self-service, но процесс снова через менеджера
- priority: Проект назван приоритетным, но нет owner / ресурсов / roadmap
- client: Боль клиента признана ключевой, но в стратегии её нет

ВАЖНО — НЕ называй это "противоречием". Формулируй строго как "сигнал к проверке":
"Документ A говорит X. Документ B говорит Y. Рекомендуем проверить: [вопрос]"

НЕ фиксируй как сигнал:
- Разные временные горизонты (квартал vs год)
- Разные уровни стратегии (операционный vs стратегический)
- Естественную эволюцию взглядов во времени

Верни JSON массив объектов:
{
  "signal_type": "strategic|operational|priority|client",
  "statement_a": "утверждение из документа A (точная цитата или тезис)",
  "statement_b": "утверждение из документа B (точная цитата или тезис)",
  "doc_index_a": 0,
  "doc_index_b": 1,
  "check_question": "Конкретный вопрос к команде",
  "severity": "critical|medium|low",
  "confidence": 0.0-1.0
}

severity — критичность по СТРОГОМУ правилу, не оценка «на глаз»:
- "critical" — прямое логическое противоречие: утверждения
  взаимоисключающие, одно отрицает другое;
- "medium" — из одних данных сделаны разные выводы или расставлены
  разные приоритеты, без прямого отрицания;
- "low" — мягкая несогласованность формулировок.

Высокий confidence (>0.8) только если конфликт очевиден и не объясняется контекстом.
Пустой массив если нет сигналов.
Только JSON, без markdown.\
"""


def _chunk_docs_for_comparison(docs_with_chunks: list[dict]) -> str:
    parts = []
    for i, d in enumerate(docs_with_chunks):
        parts.append(
            f"[Документ {i} | {d['title']} | {d['status']} | L{d['hierarchy_level']} | {d.get('created_at', '')}]\n"
            f"{d['content']}"
        )
    return "\n\n---\n\n".join(parts)


async def _comparison_text(db: AsyncSession, doc_obj) -> str:
    """Текст документа для попарного сравнения.

    Приоритет — document brief (сжатый обзор ВСЕГО документа). Раньше
    бралось 1500 символов первого чанка — этого мало: реальные
    противоречия живут в FAQ и приложениях, не во вступлении (ТЗ v1.4
    §13.7). Если брифа нет — фолбэк на склейку первых чанков.
    """
    from sqlalchemy import select as _select

    brief = (getattr(doc_obj, "brief", None) or "").strip()
    if brief:
        return brief[:8000]
    rows = await db.execute(
        _select(Chunk.content)
        .where(Chunk.document_id == doc_obj.id)
        .order_by(Chunk.chunk_index.asc())
        .limit(6)
    )
    return "\n\n".join(c for (c,) in rows.fetchall() if c)[:8000]


async def _find_signals_in_pair(doc_a: dict, doc_b: dict) -> list[dict]:
    """LLM-анализ пары документов на логические конфликты."""
    content = _chunk_docs_for_comparison([doc_a, doc_b])
    try:
        raw = await call_llm(
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": content}],
            max_tokens=4096,
        )
    except Exception as e:
        logger.error("logic_signals pair (%s × %s): LLM call failed: %s",
                     doc_a.get("id", "?")[:8], doc_b.get("id", "?")[:8], e)
        return []
    signals = parse_json_array(raw)
    if not signals:
        logger.warning("logic_signals pair: ни одного объекта не распарсилось | head=%r", raw[:200])
    return [s for s in signals if s.get("confidence", 0) >= 0.6]


def _signals_enabled() -> bool:
    """Можно отключить через env при bulk-индексации, чтобы не жечь квоту."""
    return os.getenv("DISABLE_LOGIC_SIGNALS", "").lower() not in ("1", "true", "yes")


async def find_logic_signals_for_document(
    new_doc_id: str,
    db: AsyncSession,
    max_comparisons: int = 5,
) -> list[dict]:
    """
    При загрузке нового документа — проверяем против топ-N actual документов.
    Параллелим LLM-вызовы. Можно отключить целиком env-переменной DISABLE_LOGIC_SIGNALS=1.
    """
    if not _signals_enabled():
        logger.info("logic_signals: пропущено (DISABLE_LOGIC_SIGNALS)")
        return []

    new_doc_obj = (
        await db.execute(select(Document).where(Document.id == new_doc_id))
    ).scalar_one_or_none()
    if new_doc_obj is None:
        return []

    new_doc = {
        "id": new_doc_id,
        "title": new_doc_obj.title,
        "status": new_doc_obj.status,
        "hierarchy_level": new_doc_obj.hierarchy_level or 5,
        "created_at": str(new_doc_obj.created_at or ""),
        "content": await _comparison_text(db, new_doc_obj),
    }

    existing_objs = (
        await db.execute(
            select(Document)
            .where(Document.status == "actual", Document.id != new_doc_id)
            .order_by(Document.hierarchy_level.asc())
            .limit(max_comparisons)
        )
    ).scalars().all()
    if not existing_objs:
        return []

    existing_docs = [
        {
            "id": d.id,
            "title": d.title,
            "status": d.status,
            "hierarchy_level": d.hierarchy_level or 5,
            "created_at": str(d.created_at or ""),
            "content": await _comparison_text(db, d),
        }
        for d in existing_objs
    ]

    # Параллельно опрашиваем все пары
    pair_results = await asyncio.gather(
        *[_find_signals_in_pair(new_doc, ed) for ed in existing_docs],
        return_exceptions=False,
    )

    all_signals: list[dict] = []
    for ed, raw_signals in zip(existing_docs, pair_results):
        docs = [new_doc, ed]
        for s in raw_signals:
            doc_idx_a = s.get("doc_index_a", 0)
            doc_idx_b = s.get("doc_index_b", 1)
            if doc_idx_a >= len(docs) or doc_idx_b >= len(docs):
                continue
            all_signals.append({
                "id": str(uuid.uuid4()),
                "signal_type": s.get("signal_type", "strategic"),
                "statement_a": s.get("statement_a", ""),
                "statement_b": s.get("statement_b", ""),
                "document_id_a": docs[doc_idx_a]["id"],
                "document_id_b": docs[doc_idx_b]["id"],
                "severity": s.get("severity") if s.get("severity") in ("critical", "medium", "low") else "unknown",
                "confidence": s.get("confidence", 0.7),
                "status": "open",
            })

    if all_signals:
        await save_logic_signals(db, all_signals)

    return all_signals


async def find_logic_signals_on_demand(
    query_docs: list[str],
    db: AsyncSession,
) -> list[dict]:
    """
    По явному запросу — анализируем документы из результатов RAG-поиска.
    """
    objs = (
        await db.execute(select(Document).where(Document.id.in_(query_docs)))
    ).scalars().all()
    if len(objs) < 2:
        return []

    doc_list = [
        {
            "id": d.id,
            "title": d.title,
            "status": d.status,
            "hierarchy_level": d.hierarchy_level or 5,
            "created_at": str(d.created_at or ""),
            "content": await _comparison_text(db, d),
        }
        for d in objs
    ]

    pairs = list(combinations(doc_list, 2))
    pair_results = await asyncio.gather(
        *[_find_signals_in_pair(a, b) for a, b in pairs],
        return_exceptions=False,
    )

    all_signals: list[dict] = []
    for (da, db_doc), raw in zip(pairs, pair_results):
        for s in raw:
            docs = [da, db_doc]
            doc_idx_a = s.get("doc_index_a", 0)
            doc_idx_b = s.get("doc_index_b", 1)
            if doc_idx_a >= len(docs) or doc_idx_b >= len(docs):
                continue
            all_signals.append({
                "id": str(uuid.uuid4()),
                "signal_type": s.get("signal_type", "strategic"),
                "statement_a": s.get("statement_a", ""),
                "statement_b": s.get("statement_b", ""),
                "document_id_a": docs[doc_idx_a]["id"],
                "document_id_b": docs[doc_idx_b]["id"],
                "severity": s.get("severity") if s.get("severity") in ("critical", "medium", "low") else "unknown",
                "confidence": s.get("confidence", 0.7),
                "status": "open",
            })

    return all_signals
