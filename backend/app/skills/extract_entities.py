"""Skill: extract_entities — гибрид regex + LLM.

Регекс-экстракторы детерминированно ловят числа/проценты/даты/имена.
LLM получает кандидатов как hint и обогащает их контекстом + классифицирует.
Числа которые LLM пропустил — добавляются автоматически как metric.

Это значительно точнее чистого LLM-варианта (особенно на цифровой
бухгалтерии типа таблиц), и работает быстрее за счёт меньшего числа
галлюцинаций.
"""
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

Тебе даны REGEX-КАНДИДАТЫ (числа, даты, имена, найденные программно).
Используй их как стартовую точку: классифицируй каждое и дополни контекстом.
Также добавь сущности которые regex пропустил (проекты, решения, обещания).

Типы сущностей:
- "metric": числовая метрика (name, value, unit, date_context)
- "promise": обещание/план (name, deadline)
- "person": человек (name)
- "project": проект/инициатива/продукт (name)
- "decision": решение (name)

Поля объекта:
{
  "type": "metric" | "promise" | "person" | "project" | "decision",
  "name": "оригинальное название из текста",
  "normalized_name": "lowercase без пунктуации",
  "value": "числовое значение или null",
  "unit": "единица измерения или null",
  "date_context": "YYYY-MM-DD или YYYY-MM или YYYY или null",
  "confidence": 0.0-1.0
}

Правила:
- Только то что явно в тексте
- Для метрик: всегда указывай unit и date_context если они рядом
- Для дат: ISO формат
- Не уверен — confidence ниже
- Пустой массив если нет сущностей

Ответь ТОЛЬКО JSON массивом, без markdown обёртки.\
"""

CHUNK_SIZE = 6000
MAX_CHUNKS = 8


# ── Regex-экстракторы ──────────────────────────────────────────────────────

# Число + единица. Захватываем число и единицу как группы.
_NUMBER_UNIT_RE = re.compile(
    r"(?<![а-яёa-zA-Z\d])"  # граница слева
    r"(\d+(?:[.,]\d+)?(?:\s*\d{3})?)"  # число (с пробелами для тысяч)
    r"\s*"
    r"(%|млн|млрд|тыс|k(?![a-z])|K(?![a-z])|m(?![a-z])|M(?![a-z])|"
    r"Bn|Mn|RUB|руб\.?|рублей|USD|долл\.?|FTE|"
    r"пунктов?|пункт|x|раз|кратн\w*|"
    r"шт\.?|штук|раз|чел\.?|человек)",
    re.IGNORECASE,
)

# Даты в разных форматах
_DATE_RE = re.compile(
    r"\b("
    r"Q[1-4][\s\-']?\d{2,4}|"      # Q2 2026, Q2'25
    r"\d{4}[\s\-]?[Eе]?|"          # 2030, 2030E
    r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[\s']?\d{2,4}|"
    r"(?:янв|фев|мар|апр|мая|июн|июл|авг|сен|окт|ноя|дек)[а-я]*\s*\d{2,4}|"
    r"\d{1,2}[./-]\d{1,2}[./-]\d{2,4}"
    r")\b",
    re.IGNORECASE,
)

# Имена людей: «Имя Фамилия» — две заглавные подряд слова
_PERSON_RE = re.compile(
    r"\b([А-ЯЁ][а-яё]{2,}\s+[А-ЯЁ][а-яё]{2,}"
    r"|[A-Z][a-z]{2,}\s+[A-Z][a-z]{2,})\b"
)


def _normalize_number_value(raw: str) -> str:
    """«4,2» → «4.2», «1 234» → «1234»."""
    return raw.replace(",", ".").replace(" ", "").strip()


def _extract_regex_candidates(text: str) -> dict[str, list[str]]:
    """Возвращает кандидатов по типам — для подсказки LLM."""
    numbers = []
    for m in _NUMBER_UNIT_RE.finditer(text):
        val = _normalize_number_value(m.group(1))
        unit = m.group(2).strip()
        # Берём небольшой контекст вокруг для понимания о чём метрика
        start, end = max(0, m.start() - 60), min(len(text), m.end() + 30)
        ctx = text[start:end].replace("\n", " ").strip()
        numbers.append(f"{val} {unit}  | контекст: {ctx}")

    dates = sorted({m.group(0) for m in _DATE_RE.finditer(text)})
    persons = sorted({m.group(0) for m in _PERSON_RE.finditer(text)
                       if m.group(0).lower() not in _PERSON_BLACKLIST})

    return {
        "numbers": numbers[:50],
        "dates": dates[:30],
        "persons": persons[:30],
    }


_PERSON_BLACKLIST = {
    "если да", "если нет", "то есть", "это то", "это пример",
    "в случае", "от того", "по чему", "пока что",
    "in case", "for example", "of course", "as such",
}


def _format_candidates_block(cands: dict[str, list[str]]) -> str:
    if not any(cands.values()):
        return ""
    parts = ["REGEX-КАНДИДАТЫ (из этого chunk'а):"]
    if cands.get("numbers"):
        parts.append("Числа с единицами:")
        for n in cands["numbers"][:30]:
            parts.append(f"  • {n}")
    if cands.get("dates"):
        parts.append(f"Даты: {', '.join(cands['dates'])}")
    if cands.get("persons"):
        parts.append(f"Имена-кандидаты: {', '.join(cands['persons'])}")
    return "\n".join(parts) + "\n"


# ── JSON парсинг и chunking ────────────────────────────────────────────────

def _parse_json_array(raw: str, source_label: str) -> list[dict]:
    try:
        data = json.loads(raw)
        if isinstance(data, list):
            return data
        logger.warning("entities/%s: expected JSON array, got %s", source_label, type(data).__name__)
        return []
    except json.JSONDecodeError:
        match = re.search(r"\[.*\]", raw, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError as e:
                logger.warning("entities/%s: regex-fallback failed: %s | head=%r",
                               source_label, e, raw[:200])
                return []
        logger.warning("entities/%s: invalid JSON | head=%r", source_label, raw[:200])
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


# ── Auto-add missing numbers ───────────────────────────────────────────────

def _augment_with_missing_numbers(
    llm_entities: list[dict],
    regex_numbers: list[str],
    chunk_text: str,
) -> list[dict]:
    """Добавляет в результат числа найденные регексом которые LLM пропустил.
    Гарантирует что ни одна цифра из текста не теряется."""
    # Какие числа LLM уже включил
    llm_values = set()
    for e in llm_entities:
        if e.get("type") == "metric":
            v = str(e.get("value", "")).strip().lower()
            if v:
                llm_values.add(_normalize_number_value(v))

    added = []
    for cand in regex_numbers:
        # cand имеет формат "value unit | контекст: ..."
        parts = cand.split("|", 1)
        head = parts[0].strip()
        ctx = parts[1].replace("контекст:", "").strip() if len(parts) > 1 else ""
        # Парсим value/unit
        m = re.match(r"(\S+)\s+(.+)$", head)
        if not m:
            continue
        value, unit = m.group(1), m.group(2)
        value_norm = _normalize_number_value(value)
        if value_norm in llm_values:
            continue
        # Имя метрики — короткий префикс из контекста (~60 символов)
        name = ctx[:60].strip() or f"metric_{value_norm}"
        added.append({
            "type": "metric",
            "name": name,
            "normalized_name": re.sub(r"[^\w\s]", "", name.lower()).strip(),
            "value": value_norm,
            "unit": unit,
            "date_context": None,
            "confidence": 0.65,  # ниже чем у LLM-найденных — это автодобавка
            "_source": "regex_augment",
        })
    return added


# ── Main ────────────────────────────────────────────────────────────────────

async def extract_entities_from_text(text: str) -> list[dict]:
    chunks = _chunk_text(text)
    if not chunks:
        return []

    all_entities: list[dict] = []
    total_added_by_regex = 0

    for i, chunk in enumerate(chunks):
        cands = _extract_regex_candidates(chunk)
        cand_block = _format_candidates_block(cands)
        user_content = (cand_block + "\nТЕКСТ:\n" + chunk) if cand_block else chunk

        try:
            raw = await call_llm(
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_content}],
                max_tokens=2500,
            )
        except Exception as e:
            logger.error("entities chunk %d/%d failed: %s", i + 1, len(chunks), e)
            # Если LLM упал — хотя бы числа сохраним из регекса
            from_regex = _augment_with_missing_numbers([], cands["numbers"], chunk)
            all_entities.extend(from_regex)
            total_added_by_regex += len(from_regex)
            continue

        llm_entities = _parse_json_array(raw, f"chunk{i}")
        # Дополняем недостающие числа
        augmented = _augment_with_missing_numbers(llm_entities, cands["numbers"], chunk)
        total_added_by_regex += len(augmented)
        all_entities.extend(llm_entities)
        all_entities.extend(augmented)

    if total_added_by_regex:
        logger.info("entities: regex augmented %d missing metrics", total_added_by_regex)

    # Дедуп по (type, normalized_name, value, date_context)
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
