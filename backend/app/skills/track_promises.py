"""Skill: track_promises — извлечение обещаний с чанкингом и логированием."""
from __future__ import annotations

import json
import logging
import re
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.clients import call_llm
from app.storage.sql_db import save_promises

logger = logging.getLogger(__name__)

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

CHUNK_SIZE = 6000
MAX_CHUNKS = 8


def _parse_json_array(raw: str, source_label: str) -> list[dict]:
    try:
        data = json.loads(raw)
        if isinstance(data, list):
            return data
        logger.warning("promises/%s: ожидался JSON array, получено %s", source_label, type(data).__name__)
        return []
    except json.JSONDecodeError:
        match = re.search(r"\[.*\]", raw, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError as e:
                logger.warning("promises/%s: regex-fallback не распарсился: %s | head=%r",
                               source_label, e, raw[:200])
                return []
        logger.warning("promises/%s: невалидный JSON, [] | head=%r", source_label, raw[:200])
        return []


def _chunk_text(text: str) -> list[str]:
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


async def extract_promises_from_text(
    text: str,
    document_date: str | None = None,
) -> list[dict]:
    chunks = _chunk_text(text)
    if not chunks:
        return []

    all_promises: list[dict] = []
    for i, chunk in enumerate(chunks):
        user_content = chunk
        if document_date and i == 0:
            user_content = f"Дата документа: {document_date}\n\n{chunk}"
        try:
            raw = await call_llm(
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_content}],
                max_tokens=4096,
            )
        except Exception as e:
            logger.error("promises chunk %d/%d failed: %s", i + 1, len(chunks), e)
            continue
        all_promises.extend(_parse_json_array(raw, f"chunk{i}"))

    # Дедуплицируем по нормализованной формулировке
    seen: set[str] = set()
    deduped: list[dict] = []
    for p in all_promises:
        if not isinstance(p, dict) or not p.get("text"):
            continue
        key = (p.get("normalized_text") or p["text"]).lower().strip()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(p)
    return deduped


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
