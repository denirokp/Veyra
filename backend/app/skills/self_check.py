"""Self-correction pass — после генерации ответа отдельный LLM-вызов
оценивает качество и возвращает либо OK, либо список конкретных проблем.

Если есть проблемы — основной агент пере-генерирует ответ с этим feedback'ом.
Это снижает галлюцинации (не подтверждённые факты), пропуски ключевых тем
и поверхностность.
"""
from __future__ import annotations

import json
import logging
import re

from app.clients import call_llm

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = """\
Ты — критик-проверяющий ответа аналитика корпоративной памяти.

На входе:
- ИСХОДНЫЙ ЗАПРОС пользователя
- ИСТОЧНИКИ — фрагменты документов которые видел аналитик (для проверки
  обоснованности фактов)
- ОТВЕТ — то что выдал аналитик (answer + facts + warnings + hypotheses)

Твоя задача — найти серьёзные проблемы:
1. Невыполненный запрос: запрос явно требует X, в ответе X нет/мало
2. Галлюцинации: в facts есть утверждение, которого НЕТ ни в одном источнике
3. Пропущенные ключевые числа/имена/даты которые явно есть в источниках и
   релевантны запросу — но отсутствуют в ответе
4. Противоречие внутри ответа (одна цифра в answer, другая в facts)
5. Слишком поверхностный ответ для глубокого запроса
6. Свободный текст содержит «[Источник N]», «Source 5» — это запрещённый
   формат, source_id должен быть только в facts

НЕ придирайся по мелочам. Только реальные проблемы.

Ответь СТРОГО JSON:
{
  "ok": true | false,
  "issues": ["короткое описание каждой проблемы"],
  "missing_facts": ["важные факты из источников которые стоит добавить"]
}

Если всё хорошо — {"ok": true, "issues": [], "missing_facts": []}.
Без markdown, без объяснений вокруг JSON.\
"""


async def critique(
    query: str,
    answer_payload: dict,
    sources_excerpt: str,
    max_tokens: int = 1200,
) -> dict:
    """Возвращает {ok, issues, missing_facts}."""
    # Компактуем answer payload — критику не нужно видеть полный markdown,
    # достаточно понять структуру и факты.
    facts_brief = [
        {"statement": f.statement if hasattr(f, "statement") else f.get("statement", ""),
         "source_id": getattr(getattr(f, "source", None), "title", "") if hasattr(f, "source") else None}
        for f in answer_payload.get("facts", [])[:30]
    ]
    answer_brief = {
        "answer": (answer_payload.get("answer", "") or "")[:3000],
        "facts": facts_brief,
        "warnings": answer_payload.get("warnings", []) or [],
        "hypotheses": answer_payload.get("hypotheses", []) or [],
        "requires_verification": answer_payload.get("requires_verification", []) or [],
    }
    user_msg = (
        f"ИСХОДНЫЙ ЗАПРОС:\n{query}\n\n"
        f"ИСТОЧНИКИ (фрагменты):\n{sources_excerpt[:15000]}\n\n"
        f"ОТВЕТ:\n{json.dumps(answer_brief, ensure_ascii=False, indent=2)}"
    )
    try:
        raw = await call_llm(
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_msg}],
            max_tokens=max_tokens,
        )
    except Exception as exc:
        logger.warning("self_check failed: %s", exc)
        return {"ok": True, "issues": [], "missing_facts": []}

    parsed = None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if match:
            try:
                parsed = json.loads(match.group())
            except json.JSONDecodeError:
                pass
    if not isinstance(parsed, dict):
        logger.warning("self_check: cant parse, head=%r", raw[:200])
        return {"ok": True, "issues": [], "missing_facts": []}

    return {
        "ok": bool(parsed.get("ok", True)),
        "issues": list(parsed.get("issues", []) or []),
        "missing_facts": list(parsed.get("missing_facts", []) or []),
    }
