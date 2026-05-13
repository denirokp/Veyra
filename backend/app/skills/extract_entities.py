"""Skill: extract_entities — извлечение сущностей с чанкингом и логированием."""
from __future__ import annotations

import json
import logging
import re
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.clients import call_llm
from app.skills.find_contradictions import check_and_save_contradictions
from app.storage.sql_db import save_entities

logger = logging.getLogger(__name__)

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

CHUNK_SIZE = 6000  # символов на один LLM-вызов
MAX_CHUNKS = 8     # верхняя граница — не более 48k символов суммарно (~12 стр)


def _parse_json_array(raw: str, source_label: str) -> list[dict]:
    try:
        data = json.loads(raw)
        if isinstance(data, list):
            return data
        logger.warning("entities/%s: ожидался JSON array, получено %s", source_label, type(data).__name__)
        return []
    except json.JSONDecodeError:
        match = re.search(r"\[.*\]", raw, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError as e:
                logger.warning("entities/%s: regex-fallback не распарсился: %s | head=%r",
                               source_label, e, raw[:200])
                return []
        logger.warning("entities/%s: невалидный JSON, [] | head=%r", source_label, raw[:200])
        return []


def _chunk_text(text: str) -> list[str]:
    """Режем по абзацам, чтобы не разрывать предложения. Каждый кусок ≤ CHUNK_SIZE."""
    paragraphs = text.split("\n\n")
    chunks: list[str] = []
    buffer: list[str] = []
    buffer_len = 0
    for p in paragraphs:
        plen = len(p) + 2
        if buffer_len + plen > CHUNK_SIZE and buffer:
            chunks.append("\n\n".join(buffer))
            buffer = [p]
            buffer_len = plen
        else:
            buffer.append(p)
            buffer_len += plen
        if len(chunks) >= MAX_CHUNKS:
            break
    if buffer and len(chunks) < MAX_CHUNKS:
        chunks.append("\n\n".join(buffer))
    return chunks


async def extract_entities_from_text(text: str) -> list[dict]:
    chunks = _chunk_text(text)
    if not chunks:
        return []

    all_entities: list[dict] = []
    for i, chunk in enumerate(chunks):
        try:
            raw = await call_llm(
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": chunk}],
                max_tokens=2500,
            )
        except Exception as e:
            logger.error("entities chunk %d/%d failed: %s", i + 1, len(chunks), e)
            continue
        all_entities.extend(_parse_json_array(raw, f"chunk{i}"))

    # Дедуплицируем по (type, normalized_name, value)
    seen: set[tuple] = set()
    deduped: list[dict] = []
    for e in all_entities:
        if not isinstance(e, dict) or not e.get("name"):
            continue
        key = (
            e.get("type", "other"),
            (e.get("normalized_name") or e["name"]).lower().strip(),
            str(e.get("value") or "").strip(),
            str(e.get("date_context") or "").strip(),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(e)
    return deduped


async def extract_and_save(
    text: str,
    document_id: str,
    document_metadata: dict,
    db: AsyncSession,
) -> list[dict]:
    entities = await extract_entities_from_text(text)

    rows = []
    for e in entities:
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

    metrics = [r for r in rows if r["type"] == "metric"]
    if metrics:
        await check_and_save_contradictions(metrics, document_id, db)

    return rows
