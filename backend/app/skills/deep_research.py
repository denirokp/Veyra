"""Deep research — iterative refinement по корпусу с running notebook.

Применяется когда корпус слишком большой чтобы дать LLM все полные тексты сразу
(порог: total parsed_text > 120K chars или > 10 документов). Алгоритм:

1. Router: LLM смотрит брифы всех документов + запрос → выбирает топ-N для
   глубокого анализа.
2. Iterative refinement: по каждому выбранному документу:
   - LLM видит текущий notebook (markdown) + полный текст документа + запрос
   - Обновляет notebook (добавляет новое, помечает конфликты, не дублирует).
3. Synthesis: финальный LLM-вызов превращает notebook в структурированный
   ChatResponse (answer, facts, warnings, hypotheses, requires_verification).

Идея: LLM никогда не перегружен — видит компактный notebook + один документ.
Notebook растёт по мере чтения. Работает на 500 документах так же как на 5,
просто медленнее.
"""
from __future__ import annotations

import json
import logging
import re
import time
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.clients import call_llm
from app.storage.sql_db import (
    Document,
    get_all_document_briefs,
    get_all_document_full_texts,
    get_document,
)

logger = logging.getLogger(__name__)


# Маркер пустого notebook — для самого первого документа
EMPTY_NOTEBOOK = """\
# Блокнот аналитика

## Ключевые факты и цифры
(пусто)

## Инициативы и стримы
(пусто)

## Владельцы и ответственные
(пусто)

## Сроки и дедлайны
(пусто)

## Риски и расхождения
(пусто)

## Открытые вопросы / next steps
(пусто)
"""


ROUTER_SYSTEM = """\
Ты — координатор анализа корпоративной базы знаний. На входе:
- запрос пользователя
- список документов с их короткими обзорами (briefs)

Твоя задача: ВЫБРАТЬ документы, которые нужно глубоко прочитать для ответа.

Правила:
1. Выбирай 5-10 документов (можно меньше если корпус маленький).
2. Приоритет: документы с явно релевантным содержанием по обзору.
3. Если запрос требует широкого охвата (полный разбор, что нового, тренды) —
   бери разнообразные документы из разных тем.
4. Возвращай СТРОГО JSON-массив объектов:
   [{"doc_id": "...", "reason": "одно предложение почему"}]
5. Никакого markdown, никаких комментариев. Только JSON.\
"""


REFINE_SYSTEM = """\
Ты — аналитик с блокнотом. На входе:
- запрос пользователя
- ТЕКУЩИЙ БЛОКНОТ (markdown с накопленными наблюдениями из ранее прочитанных
  документов)
- ОДИН НОВЫЙ ДОКУМЕНТ целиком

Твоя задача: обновить блокнот, добавив всё новое и ценное из этого документа.

Правила:
1. НЕ дублируй то что уже есть в блокноте (если факт повторяется — пропусти).
2. КАЖДЫЙ пункт начинай с [Название документа] чтобы было видно откуда.
3. Если новый документ ПРОТИВОРЕЧИТ блокноту — добавь в секцию "Риски и
   расхождения" с пометкой какие документы дают разные значения.
4. Числа давай с единицами и периодом.
5. Имена ответственных копируй точно.
6. НЕ выдумывай — только то что явно есть в документе.
7. Сохраняй структуру блокнота (6 секций). Если в секцию нечего добавить —
   оставь её как есть.
8. ВЕРНИ ОБНОВЛЁННЫЙ БЛОКНОТ ЦЕЛИКОМ как markdown. Без преамбулы, без
   объяснений.\
"""


SYNTHESIS_SYSTEM = """\
Ты — аналитик корпоративной памяти. На входе:
- запрос пользователя
- БЛОКНОТ — полный набор фактов/инициатив/рисков/имён собранный из
  множества документов
- ФРАГМЕНТЫ — отдельные куски документов с source_id для цитирования

Задача: превратить блокнот в развёрнутый структурированный ответ.

ФОРМАТ — строго валидный JSON:
{
  "answer": "5-8 предложений: суть, статус, ключевые цифры, главные владельцы",
  "facts": [
    {"statement": "конкретный факт с числом или именем", "source_id": 1}
  ],
  "hypotheses": ["рыночный контекст, аналоги, твои предположения с disclaimer"],
  "warnings": ["расхождения данных, риски, противоречия из блокнота"],
  "requires_verification": ["что не закрыто, что критично проверить"]
}

Правила:
1. facts: МИНИМУМ 12-20 пунктов. Покрой ВСЕ темы из блокнота.
2. Каждый факт — source_id из ФРАГМЕНТОВ (целое число). Если точного
   фрагмента нет — ставь source_id ближайшего релевантного.
3. source_id используется ТОЛЬКО внутри объектов facts. В строках
   answer/hypotheses/warnings/requires_verification ЗАПРЕЩЕНО упоминать
   "[Источник N]", "Source 5", "(см. 3)" и т.п. Если нужно атрибутировать —
   пиши название документа словами.
4. ПРАВИЛА СРАВНЕНИЯ МЕТРИК: помечай "расхождение" в warnings ТОЛЬКО
   если совпадают имя метрики, период и единица, но значения разные.
   Разные метрики с похожим словом (TRI*M vs CES) — НЕ расхождение.
5. answer не повторяет facts.
6. НЕ выдумывай. Только из блокнота и фрагментов.
7. Ответь ТОЛЬКО JSON, без markdown-обёртки.\
"""


def _parse_json_array(raw: str) -> list[dict]:
    try:
        data = json.loads(raw)
        return data if isinstance(data, list) else []
    except json.JSONDecodeError:
        match = re.search(r"\[.*\]", raw, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                return []
        return []


async def _select_relevant_docs(
    query: str,
    briefs: list[tuple[Document, str]],
    max_select: int = 10,
) -> list[str]:
    """Router-шаг: LLM выбирает топ-N документов для глубокого чтения."""
    if not briefs:
        return []
    if len(briefs) <= max_select:
        # Корпус маленький — берём все
        return [doc.id for doc, _ in briefs]

    brief_lines = [
        f"=== doc_id: {doc.id}\nЗаголовок: {doc.title}\nСтатус: {doc.status}, Уровень: L{doc.hierarchy_level or 5}\nОбзор:\n{brief}"
        for doc, brief in briefs
    ]
    user_msg = (
        f"ЗАПРОС ПОЛЬЗОВАТЕЛЯ:\n{query}\n\n"
        f"ДОКУМЕНТЫ В БАЗЕ ({len(briefs)} шт):\n\n"
        + "\n\n".join(brief_lines)
        + f"\n\nВыбери до {max_select} doc_id для глубокого чтения."
    )
    raw = await call_llm(
        system=ROUTER_SYSTEM,
        messages=[{"role": "user", "content": user_msg}],
        max_tokens=2000,
    )
    items = _parse_json_array(raw)
    valid_ids = {doc.id for doc, _ in briefs}
    return [it["doc_id"] for it in items
            if isinstance(it, dict) and it.get("doc_id") in valid_ids][:max_select]


DOC_TEXT_PER_ITERATION = 40_000  # обрезка одного документа в iteration шаге


async def _refine_notebook(
    query: str,
    notebook: str,
    doc: Document,
    doc_text: str,
) -> str:
    """Один шаг итеративного refinement: обновляем notebook новым документом."""
    truncated = doc_text[:DOC_TEXT_PER_ITERATION]
    if len(doc_text) > DOC_TEXT_PER_ITERATION:
        truncated += f"\n\n[...документ урезан до {DOC_TEXT_PER_ITERATION} символов]"

    user_msg = (
        f"ЗАПРОС ПОЛЬЗОВАТЕЛЯ:\n{query}\n\n"
        f"ТЕКУЩИЙ БЛОКНОТ:\n{notebook}\n\n"
        f"=== НОВЫЙ ДОКУМЕНТ: «{doc.title}» (status={doc.status}, L{doc.hierarchy_level or 5}) ===\n"
        f"{truncated}\n\n"
        "Обнови блокнот по правилам в system prompt. Верни блокнот целиком."
    )
    return await call_llm(
        system=REFINE_SYSTEM,
        messages=[{"role": "user", "content": user_msg}],
        max_tokens=4000,
    )


_SRC_REF_PATTERNS = [
    re.compile(r"\s*\[Источник\s*\d+(?:\s*\|[^\]]*)?\]", re.IGNORECASE),
    re.compile(r"\s*\(Источник\s*\d+\)", re.IGNORECASE),
    re.compile(r"\s*\[Source\s*\d+(?:\s*\|[^\]]*)?\]", re.IGNORECASE),
    re.compile(r"\s*\(Source\s*\d+\)", re.IGNORECASE),
    re.compile(r"\s*\[doc:[^\]]+\]"),
]


def _strip_src_refs(value: Any) -> Any:
    """Вычищает артефакты типа [Источник 5] из строк ответа.
    source_id допустим только внутри facts.source_id (число)."""
    if isinstance(value, str):
        for p in _SRC_REF_PATTERNS:
            value = p.sub("", value)
        return re.sub(r"\s+", " ", value).strip()
    if isinstance(value, list):
        return [_strip_src_refs(v) for v in value]
    return value


async def _synthesize(query: str, notebook: str, chunks_context: str) -> dict:
    """Финальный шаг: notebook → структурированный ChatResponse."""
    user_msg = (
        f"ЗАПРОС:\n{query}\n\n"
        f"БЛОКНОТ (накопленный из всех документов):\n{notebook}\n\n"
        f"ФРАГМЕНТЫ ДЛЯ ЦИТИРОВАНИЯ:\n{chunks_context}\n\n"
        "Превратите блокнот в финальный JSON-ответ."
    )
    raw = await call_llm(
        system=SYNTHESIS_SYSTEM,
        messages=[{"role": "user", "content": user_msg}],
        max_tokens=4000,
    )
    parsed: dict | None = None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if match:
            try:
                parsed = json.loads(match.group())
            except json.JSONDecodeError:
                pass
    if not parsed:
        logger.warning("deep_research: synthesis JSON parse failed, head=%r", raw[:200])
        return {"answer": raw, "facts": [], "hypotheses": [], "warnings": [], "requires_verification": []}

    # Пост-фильтр source-ссылок в free-text полях
    parsed["answer"] = _strip_src_refs(parsed.get("answer", ""))
    parsed["hypotheses"] = _strip_src_refs(parsed.get("hypotheses", []) or [])
    parsed["warnings"] = _strip_src_refs(parsed.get("warnings", []) or [])
    parsed["requires_verification"] = _strip_src_refs(parsed.get("requires_verification", []) or [])
    return parsed


async def run_deep_research(
    query: str,
    db: AsyncSession,
    chunks_context: str = "",
    max_docs: int = 10,
) -> dict:
    """Полный pipeline: router → iterative refinement → synthesis.
    Возвращает dict с ключами answer/facts/hypotheses/warnings/requires_verification.
    """
    t0 = time.monotonic()

    # Шаг 1: router по брифам
    briefs = await get_all_document_briefs(db, statuses=["actual"], limit=200)
    if not briefs:
        logger.warning("deep_research: no briefs available, нечего анализировать")
        return {
            "answer": "В базе нет документов с брифами. Загрузите документы или вызовите backfill.",
            "facts": [], "hypotheses": [], "warnings": [], "requires_verification": [],
        }

    selected_ids = await _select_relevant_docs(query, briefs, max_select=max_docs)
    logger.info("deep_research: router picked %d/%d docs in %.1fs",
                len(selected_ids), len(briefs), time.monotonic() - t0)

    if not selected_ids:
        # Fallback: берём топ-N по индексу
        selected_ids = [doc.id for doc, _ in briefs[:max_docs]]

    # Загружаем полные тексты выбранных
    all_texts = await get_all_document_full_texts(db, statuses=["actual"], limit=500)
    text_by_id = {doc.id: (doc, text) for doc, text in all_texts}

    # Шаг 2: iterative refinement
    notebook = EMPTY_NOTEBOOK
    for i, doc_id in enumerate(selected_ids):
        if doc_id not in text_by_id:
            logger.warning("deep_research: doc=%s has no parsed_text, skipping", doc_id)
            continue
        doc, text = text_by_id[doc_id]
        ts = time.monotonic()
        try:
            notebook = await _refine_notebook(query, notebook, doc, text)
        except Exception as exc:
            logger.error("deep_research: refine failed on %s: %s", doc.title, exc)
            continue
        logger.info("deep_research: refined with doc %d/%d (%s) in %.1fs",
                    i + 1, len(selected_ids), doc.title, time.monotonic() - ts)

    # Шаг 3: synthesis
    ts = time.monotonic()
    result = await _synthesize(query, notebook, chunks_context)
    logger.info("deep_research: synthesis in %.1fs, total %.1fs",
                time.monotonic() - ts, time.monotonic() - t0)
    return result
