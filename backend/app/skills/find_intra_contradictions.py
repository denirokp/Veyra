"""Skill: find_intra_contradictions — ЛОГИЧЕСКИЕ расхождения ВНУТРИ документа.

Скан полного текста одного документа на пары утверждений, которые логически
несовместимы (одно отрицает другое, противоположные выводы из одних данных).

Числовые внутридокументные расхождения здесь больше НЕ ищутся. Раньше их
искал LLM по полному тексту — и фабриковал значения, которых в документе
нет (precision 11% на валидации). Числовые расхождения — и кросс-, и
внутридокументные — теперь находит детерминированный `find_contradictions`
по таблице Entity, без LLM.

Логика пишется в logic_signals с document_id_a == document_id_b.
"""
from __future__ import annotations

import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.clients import call_llm, parse_json_array
from app.storage.sql_db import save_logic_signals

logger = logging.getLogger(__name__)

# Документ целиком; для очень больших — обрезаем (≈30K токенов запас).
MAX_DOC_CHARS = 120_000
MIN_CONFIDENCE = 0.6

SYSTEM_PROMPT = """\
Ты аналитик-ревизор ОДНОГО документа. Найди ВНУТРЕННИЕ ЛОГИЧЕСКИЕ
расхождения — пары утверждений документа, которые логически несовместимы:
одно отрицает другое, либо из одних и тех же данных сделаны противоположные
выводы.

НЕ считать расхождением:
- разные периоды (Q1 vs Q4) — это эволюция во времени;
- план vs факт, если это явно так помечено;
- числовые расхождения (одна метрика — разные числа): их ищет отдельный
  детектор, здесь ТОЛЬКО логика.

Для КАЖДОЙ находки дай ТОЧНЫЕ ЦИТАТЫ обоих мест документа.

Верни СТРОГО JSON-массив, без markdown:
[{
  "statement_a": "точная цитата места 1",
  "statement_b": "точная цитата места 2",
  "confidence": 0.0-1.0
}]

Высокий confidence только при очевидном расхождении. Пустой массив [],
если внутренних логических расхождений нет.\
"""


async def find_intra_contradictions(
    document_id: str,
    full_text: str,
    db: AsyncSession,
) -> int:
    """Скан одного документа на внутренние логические расхождения. Пишет
    находки в logic_signals. Возвращает число находок."""
    if not full_text or not full_text.strip():
        return 0

    try:
        raw = await call_llm(
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": full_text[:MAX_DOC_CHARS]}],
            max_tokens=4096,
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("intra_contradictions doc=%s: LLM call failed: %s",
                     document_id[:8], exc)
        return 0

    logic_rows: list[dict] = []
    for f in parse_json_array(raw):
        conf = float(f.get("confidence", 0.7) or 0.7)
        if conf < MIN_CONFIDENCE:
            continue
        statement_a = str(f.get("statement_a") or f.get("value_a") or "").strip()
        statement_b = str(f.get("statement_b") or f.get("value_b") or "").strip()
        if not statement_a or not statement_b:
            continue
        logic_rows.append({
            "id": str(uuid.uuid4()),
            "signal_type": "intra-document",
            "statement_a": statement_a,
            "statement_b": statement_b,
            "document_id_a": document_id,
            "document_id_b": document_id,
            "confidence": conf,
            "status": "open",
        })

    if logic_rows:
        await save_logic_signals(db, logic_rows)

    logger.info("intra_contradictions doc=%s → logic=%d",
                document_id[:8], len(logic_rows))
    return len(logic_rows)
