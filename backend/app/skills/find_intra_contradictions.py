"""Skill: find_intra_contradictions — числовые и логические расхождения
ВНУТРИ одного документа.

Зачем отдельный детектор. Находки класса N-02 (одна метрика с разными
значениями в FAQ и в приложении одного документа) retrieval не достаёт
надёжно: запрос не содержит саму константу, а табличный чанк приложения
не всплывает в топе. Но один документ целиком (~50K символов) свободно
влезает в контекст LLM. Поэтому скан идёт по ПОЛНОМУ тексту одного
документа за раз — это и масштабируется (O(n) по документам), и не
зависит от retrieval (ТЗ v1.4, блок C).

Результат пишется в те же таблицы, что и кросс-документные находки:
numeric → contradictions, logic → logic_signals, с document_id_a ==
document_id_b (обе ссылки на сам документ). Чат подхватывает их через
entity-memory автоматически.
"""
from __future__ import annotations

import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.clients import call_llm, parse_json_array
from app.settings import settings
from app.storage.sql_db import save_contradiction, save_logic_signals

logger = logging.getLogger(__name__)

# Документ целиком; для очень больших — обрезаем (≈30K токенов запас).
MAX_DOC_CHARS = 120_000
MIN_CONFIDENCE = 0.6

SYSTEM_PROMPT = """\
Ты аналитик-ревизор ОДНОГО документа. Найди ВНУТРЕННИЕ расхождения —
противоречия ВНУТРИ этого документа (не с другими документами).

ДВА типа:
1. numeric — одна и та же метрика (одно имя, один период, одна единица)
   имеет РАЗНЫЕ значения в разных местах документа.
   Пример: в FAQ «churn 7%», а в приложении финмодель считает по «5,54%».
2. logic — два утверждения документа логически несовместимы.

НЕ считать расхождением:
- разные периоды (Q1 vs Q4) — это эволюция во времени;
- разные единицы измерения (% vs руб);
- разные метрики с похожим названием;
- план vs факт, если это явно так помечено.

Для КАЖДОЙ находки дай ТОЧНЫЕ ЦИТАТЫ обоих мест документа.

Верни СТРОГО JSON-массив, без markdown:
[{
  "type": "numeric" | "logic",
  "metric": "имя метрики (для numeric; для logic — null)",
  "value_a": "значение или цитата места 1",
  "value_b": "значение или цитата места 2",
  "statement_a": "точная цитата места 1",
  "statement_b": "точная цитата места 2",
  "period": "период если есть, иначе null",
  "confidence": 0.0-1.0
}]

Высокий confidence только при очевидном расхождении. Пустой массив [],
если внутренних расхождений нет.\
"""


async def find_intra_contradictions(
    document_id: str,
    full_text: str,
    db: AsyncSession,
) -> int:
    """Скан одного документа на внутренние расхождения. Пишет numeric в
    contradictions, logic в logic_signals. Возвращает общее число находок."""
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

    findings = [
        f for f in parse_json_array(raw)
        if float(f.get("confidence", 0.7) or 0.7) >= MIN_CONFIDENCE
    ]

    numeric_rows: list[dict] = []
    logic_rows: list[dict] = []
    for f in findings:
        ftype = (f.get("type") or "").strip().lower()
        conf = float(f.get("confidence", 0.7) or 0.7)
        if ftype == "numeric":
            # Числовой детектор отключён по умолчанию (precision 11% на
            # валидации) — см. ENABLE_NUMERIC_CONTRADICTIONS в settings.py.
            if not settings.ENABLE_NUMERIC_CONTRADICTIONS:
                continue
            numeric_rows.append({
                "id": str(uuid.uuid4()),
                "metric": f.get("metric") or "внутреннее числовое расхождение",
                "value_a": str(f.get("value_a") or f.get("statement_a") or ""),
                "value_b": str(f.get("value_b") or f.get("statement_b") or ""),
                "document_id_a": document_id,
                "document_id_b": document_id,
                "period": f.get("period"),
                "status": "open",
            })
        else:
            # logic или неизвестный тип — трактуем как логическое расхождение
            logic_rows.append({
                "id": str(uuid.uuid4()),
                "signal_type": "intra-document",
                "statement_a": str(f.get("statement_a") or f.get("value_a") or ""),
                "statement_b": str(f.get("statement_b") or f.get("value_b") or ""),
                "document_id_a": document_id,
                "document_id_b": document_id,
                "confidence": conf,
                "status": "open",
            })

    for row in numeric_rows:
        await save_contradiction(db, row)
    if logic_rows:
        await save_logic_signals(db, logic_rows)

    logger.info("intra_contradictions doc=%s → numeric=%d logic=%d",
                document_id[:8], len(numeric_rows), len(logic_rows))
    return len(numeric_rows) + len(logic_rows)
