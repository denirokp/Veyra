"""Docs Agent — RAG поиск + LLM генерация с ФАКТ/ГИПОТЕЗА структурой."""
from __future__ import annotations

import json
import logging
import re

from sqlalchemy.ext.asyncio import AsyncSession

from app.clients import call_llm
from app.models.schemas import ChatMode, ChatResponse, FactItem, SourceRef
from app.rag.retriever import RetrievedChunk, retrieve
from app.storage.sql_db import (
    get_document,
    get_open_contradictions_for_docs,
    search_entities_by_query,
)

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
Ты аналитик корпоративной памяти команды Avito. У тебя есть доступ к внутренним \
документам команды — стратегиям, ресёрчам, операционным планам.

ПРАВИЛА (соблюдай строго):
1. Используй ТОЛЬКО информацию из предоставленных фрагментов документов
2. Каждое фактическое утверждение ОБЯЗАТЕЛЬНО сопровождай ссылкой на источник
3. Разделяй ФАКТЫ (есть в документах) и ГИПОТЕЗЫ (твои предположения)
4. Archived и draft — используй только как контекст с явным предупреждением
5. Если данных недостаточно — напиши это явно, не придумывай

ФОРМАТ ОТВЕТА — строго JSON:
{
  "answer": "Прямой ответ на вопрос в 1-3 предложениях",
  "facts": [
    {
      "statement": "Конкретное утверждение из документа",
      "source_id": 1
    }
  ],
  "hypotheses": ["Предположение которого нет в документах явно"],
  "warnings": ["⚠️ Если использованы archived/draft данные или есть конфликт"],
  "requires_verification": ["Вопрос если данных недостаточно"]
}

source_id — это НОМЕР источника (1, 2, 3...) из заголовка [Источник N] в контексте выше. \
source_id используется ТОЛЬКО внутри объектов facts, как поле "source_id": N. \
В строках answer/hypotheses/warnings/requires_verification ЗАПРЕЩЕНО упоминать \
номера источников вида "[Источник 5]", "Source 7", "(см. 3)" и т.п. — пиши \
название документа или раздел словами, если нужно атрибутировать.

ПРАВИЛА СРАВНЕНИЯ МЕТРИК (важно):
- Помечай как "расхождение" в warnings ТОЛЬКО если одна и та же метрика \
(совпадают имя ИЛИ нормализованное имя), один и тот же период, одна и та же \
единица — имеет разные значения в разных документах.
- Разные метрики с похожим словом в названии (например TRI*M -12 vs CES -16) — \
это НЕ расхождение, это две разные метрики. Не сравнивай их.
- Разные периоды (Q2'25 vs Q4'25) — НЕ расхождение, это эволюция во времени.
- Разные единицы (% vs руб) — НЕ расхождение.

Отвечай ТОЛЬКО валидным JSON. Без markdown-обёртки.\
"""

MODE_INSTRUCTIONS: dict[ChatMode, str] = {
    ChatMode.search: (
        "Найди и синтезируй всё что есть в документах по заданной теме. "
        "Если данных мало — дай что есть и не выдумывай недостающее, "
        "в requires_verification перечисли что не учтено в текущих планах и где "
        "есть риск расхождения плана с реальностью. "
        "Если видишь противоречия в данных — отметь в warnings."
    ),
    ChatMode.contradictions: (
        "Найди числовые и смысловые расхождения по теме между документами. "
        "В facts перечисли разные цифры/тезисы с указанием каждого источника. "
        "В warnings — каждое расхождение отдельной строкой. "
        "Если в базе пока один документ — поищи внутренние нестыковки в нём "
        "(разные значения одной метрики в разных разделах, противоречивые "
        "утверждения). Если нестыковок нет — честно скажи это в answer."
    ),
    ChatMode.promises: (
        "Найди все обещания, планы и дедлайны по теме. "
        "Для каждого: точная цитата, документ, срок если указан, "
        "ответственный если указан. "
        "В warnings — отметь просроченные, без дедлайна, без владельца. "
        "Если обещаний не нашлось — скажи это явно в answer."
    ),
    ChatMode.gaps: (
        "Найди серые зоны: темы которые упомянуты/изучены, но не вошли в "
        "стратегию или план; риски не закрытые мерами; внешние факторы "
        "не учтённые в документах. "
        "В facts — то что обсуждалось но недопроработано. "
        "В requires_verification — что критично проверить. "
        "Если корпус мал, опирайся на здравый смысл и помечай это в hypotheses."
    ),
    ChatMode.write: (
        "Ты помогаешь написать документ. "
        "Собери все релевантные факты из документов для использования в тексте. "
        "В answer — готовый абзац/тезисы под копипаст в стилистике команды."
    ),
    ChatMode.validate: (
        "Оцени инициативу на основе документов. "
        "Укажи: что уже изучали по теме, что противоречит идее, что поддерживает. "
        "В requires_verification — конкретные вопросы которые нужно проверить перед запуском. "
        "В hypotheses — рыночный контекст и аналоги."
    ),
    ChatMode.research: (
        "Собери всё что есть в документах по теме включая архивные. "
        "Дополни рыночным контекстом — конкуренты, тренды, как делают другие "
        "(это твои знания, помечай как hypotheses с disclaimer). "
        "Ищи паттерны, повторяющиеся проблемы."
    ),
    ChatMode.full: (
        "Сделай ГЛУБОКИЙ РЕСЁРЧ-ОТЧЁТ. Пользователь ждёт не список цитат, "
        "а полноценный аналитический документ под копипаст в Confluence.\n\n"
        "У ТЕБЯ ДВА ИСТОЧНИКА КОНТЕКСТА:\n"
        "(А) ПОЛНЫЕ ТЕКСТЫ или ОБЗОРЫ документов — первичный источник. "
        "Анализируй ЦЕЛИКОМ каждый документ. Не пропускай таблицы, риски, "
        "appendix, имена, конкретные цифры из ячеек.\n"
        "(Б) ФРАГМЕНТЫ — нумерованные куски для source_id в facts.\n\n"
        "ФОРМАТ ПОЛЯ answer — markdown-отчёт на 800-1500 слов со следующей "
        "структурой (используй именно эти заголовки H2):\n"
        "## Резюме (TL;DR)\n"
        "3-5 предложений: суть, ключевые цифры, статус.\n\n"
        "## Контекст и проблематика\n"
        "Что описано в документах: проблемы, точки боли, причины. Цифры с "
        "единицами и периодами. Цитируй конкретные значения.\n\n"
        "## Ключевые инициативы и направления\n"
        "Структурированный разбор стримов/волн/проектов. Используй подзаголовки "
        "H3 для каждого направления. Указывай владельцев, ожидаемые эффекты, "
        "сроки.\n\n"
        "## Метрики и ожидаемые результаты\n"
        "Таблица или список с цифрами целей. Из каких источников выводы.\n\n"
        "## Риски и расхождения\n"
        "Что может пойти не так, какие риски прямо отмечены в документах "
        "(probability/impact если есть), любые внутренние противоречия.\n\n"
        "## Внешний рыночный контекст и аналоги\n"
        "Конкуренты, бенчмарки, best practices. Если в документах есть "
        "competitor analysis — суммируй; иначе твои знания с disclaimer "
        "(пометь как hypothesis).\n\n"
        "## Рекомендации и план действий\n"
        "Конкретные следующие шаги, приоритизация. Что сделать в первую "
        "очередь, что во вторую. Опирайся на данные документов.\n\n"
        "## Открытые вопросы и серые зоны\n"
        "Что ещё не закрыто, у каких инициатив нет owner/deadline/метрик, "
        "что критично проверить.\n\n"
        "ОСТАЛЬНЫЕ ПОЛЯ JSON:\n"
        "- facts: МИНИМУМ 15-20 фактов. По каждому документу минимум 5-8. "
        "Тут структурированные цитаты с source_id для дальнейшей навигации. "
        "answer и facts дополняют друг друга, не дублируйте 1:1.\n"
        "- warnings: список расхождений/рисков отдельной строкой.\n"
        "- hypotheses: рыночные предположения с disclaimer.\n"
        "- requires_verification: что не закрыто/не назначено/нужно проверить.\n\n"
        "ПРАВИЛА:\n"
        "- НЕ округляй цифры, копируй точно из документов.\n"
        "- НЕ выдумывай факты. Где гипотеза — явно пометь.\n"
        "- В answer markdown — используй H2/H3, списки, **жирный** для ключевых "
        "цифр, --- разделители если уместно.\n"
        "- В answer НЕ пиши [Источник N] — пиши название документа.\n"
        "- Если две цифры одной метрики в разных документах — обе в facts + "
        "одна warning о расхождении (только при совпадении period+unit)."
    ),
}


def _build_context(chunks: list[RetrievedChunk]) -> str:
    parts = []
    for i, c in enumerate(chunks):
        status_label = c.status.upper()
        level_label = f"L{c.hierarchy_level}"
        title = c.title or c.document_id[:8]
        section = f" / {c.section}" if c.section else ""
        parts.append(
            f"[Источник {i+1} | {title}{section} | {status_label} | {level_label}]\n"
            f"{c.content}"
        )
    return "\n\n---\n\n".join(parts)


def _build_entity_memory_block(entities: list, contradictions: list) -> str:
    """Формирует блок entity memory для добавления в промпт."""
    if not entities and not contradictions:
        return ""

    lines = ["[ENTITY MEMORY — известные факты из документов]"]

    if entities:
        lines.append("Метрики и сущности:")
        for e in entities[:15]:
            val = f" = {e.value}" if e.value else ""
            unit = f" {e.unit}" if e.unit else ""
            date = f" ({e.date_context})" if e.date_context else ""
            lines.append(f"  • {e.name}{val}{unit}{date} [doc:{e.document_id[:8]}...]")

    if contradictions:
        lines.append("Известные расхождения по этим документам:")
        for c in contradictions[:5]:
            lines.append(
                f"  ⚠ {c.metric}: {c.value_a} vs {c.value_b} "
                f"[doc:{c.document_id_a[:8]} vs doc:{c.document_id_b[:8]}]"
            )

    return "\n".join(lines)


async def _parse_llm_response(
    raw: str,
    chunks: list[RetrievedChunk],
    db: AsyncSession,
) -> tuple[str, list[FactItem], list[str], list[str], list[str]]:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group())
            except json.JSONDecodeError as e:
                logger.warning("docs_agent: regex-fallback не распарсился: %s | head=%r", e, raw[:200])
                return raw, [], [], ["⚠️ Не удалось разобрать структурированный ответ"], []
        else:
            logger.warning("docs_agent: невалидный JSON | head=%r", raw[:200])
            return raw, [], [], ["⚠️ Не удалось разобрать структурированный ответ"], []

    # Пост-фильтр: вычищаем артефакты типа [Источник 5] / (Source 7) / [doc:abc]
    # которые LLM иногда вставляет в free-text вопреки правилам в system prompt.
    _src_ref_patterns = [
        re.compile(r"\s*\[Источник\s*\d+(?:\s*\|[^\]]*)?\]", re.IGNORECASE),
        re.compile(r"\s*\(Источник\s*\d+\)", re.IGNORECASE),
        re.compile(r"\s*\[Source\s*\d+(?:\s*\|[^\]]*)?\]", re.IGNORECASE),
        re.compile(r"\s*\(Source\s*\d+\)", re.IGNORECASE),
        re.compile(r"\s*\[doc:[^\]]+\]"),
    ]

    def _clean_str(s: str) -> str:
        for p in _src_ref_patterns:
            s = p.sub("", s)
        # Не схлопываем переводы строк — нужны для markdown в answer
        s = re.sub(r"[ \t]+", " ", s)
        s = re.sub(r"\n{3,}", "\n\n", s)
        return s.strip()

    def _as_str_list(raw):
        # LLM иногда возвращает элементы как dict {statement, source_id} —
        # схема ждёт строки, приводим вручную. Заодно вычищаем артефакты
        # source-ссылок в свободном тексте.
        out = []
        for w in raw or []:
            if not w:
                continue
            if isinstance(w, str):
                cleaned = _clean_str(w)
            elif isinstance(w, dict):
                raw_str = w.get("statement") or w.get("text") or str(w)
                cleaned = _clean_str(raw_str)
            else:
                cleaned = _clean_str(str(w))
            if cleaned:
                out.append(cleaned)
        return out

    answer = _clean_str(data.get("answer", ""))
    hypotheses = _as_str_list(data.get("hypotheses"))
    warnings = _as_str_list(data.get("warnings"))
    requires = _as_str_list(data.get("requires_verification"))

    # Индексный map: номер источника (1-based) → chunk
    index_map: dict[int, RetrievedChunk] = {i + 1: c for i, c in enumerate(chunks)}

    facts: list[FactItem] = []
    for f in data.get("facts", []):
        if not isinstance(f, dict) or not f.get("statement"):
            continue

        # source_id теперь целое число — номер источника
        try:
            source_num = int(f.get("source_id", 0))
        except (TypeError, ValueError):
            source_num = 0
        chunk = index_map.get(source_num)

        if chunk:
            doc_row = await get_document(db, chunk.document_id)
            # SourceRef.document_id типизирован как UUID, а в Chroma могли
            # попасть не-UUID id (старые тестовые прогоны и т.п.) — подменяем
            # на nil-UUID и сохраняем оригинал в title.
            from uuid import UUID as _UUID
            try:
                doc_uuid = _UUID(str(chunk.document_id))
            except (TypeError, ValueError):
                doc_uuid = _UUID("00000000-0000-0000-0000-000000000000")
            source = SourceRef(
                document_id=doc_uuid,
                title=doc_row.title if doc_row else (chunk.title or chunk.document_id),
                status=chunk.status,  # type: ignore[arg-type]
                hierarchy_level=chunk.hierarchy_level,
                section=chunk.section or None,
                confluence_url=doc_row.confluence_url if doc_row else None,
            )
        else:
            # Если LLM не дал валидный номер — ставим заглушку, не теряем факт
            from uuid import UUID as _UUID
            source = SourceRef(
                document_id=_UUID("00000000-0000-0000-0000-000000000000"),
                title="Источник не определён",
                status="unknown",  # type: ignore[arg-type]
                hierarchy_level=5,
            )

        facts.append(FactItem(statement=f["statement"], source=source))

    return answer, facts, hypotheses, warnings, requires


async def run(
    message: str,
    mode: ChatMode,
    file_content: str | None = None,
    db: AsyncSession | None = None,
    history=None,
    style: str = "report",
) -> dict:
    # Поиск релевантных чанков — для full режима берём больше материала,
    # чтобы LLM мог достать конкретные числа и атрибуцию.
    include_archive = mode in (ChatMode.search, ChatMode.gaps, ChatMode.contradictions)
    top_k = 30 if mode == ChatMode.full else 15
    chunks = await retrieve(message, top_k=top_k, include_archive=include_archive)

    # Document-level контекст для full mode имеет 3 стратегии в зависимости
    # от размера корпуса:
    #   1) корпус влезает целиком (≤120K chars) → ПОЛНЫЕ ТЕКСТЫ
    #   2) средний (≤30 доков, не помещается) → ОБЗОРЫ (briefs)
    #   3) большой (>30 доков или брифов > 100K chars) → deep_research:
    #      router выбирает топ-N, потом iterative refinement по их полным
    #      текстам, потом synthesis. Возвращаем результат deep_research как
    #      финальный ответ, минуя обычный LLM-вызов в этой функции.
    doc_briefs_block = ""
    full_texts_block = ""
    if mode == ChatMode.full and db is not None:
        FULL_TEXTS_BUDGET = 120_000

        from app.storage.sql_db import (
            get_all_document_briefs,
            get_all_document_full_texts,
        )
        full_texts = await get_all_document_full_texts(db, statuses=["actual"], limit=20)
        total = sum(len(t) for _, t in full_texts)
        n_docs = len(full_texts)

        # Стратегия 1: всё влезает — даём полные тексты LLM напрямую
        if full_texts and total <= FULL_TEXTS_BUDGET and n_docs <= 20:
            parts = [
                f"=== ПОЛНЫЙ ТЕКСТ: {doc.title} (L{doc.hierarchy_level or 5}, {doc.status}) ===\n{text}"
                for doc, text in full_texts
            ]
            full_texts_block = "\n\n".join(parts)
            logger.info("full-mode: using %d full texts (%d chars total)", n_docs, total)
        else:
            # Стратегия 2 vs 3: проверяем сколько brief'ов есть
            briefs = await get_all_document_briefs(db, statuses=["actual"], limit=500)
            briefs_total = sum(len(b) for _, b in briefs)

            # Стратегия 3: корпус большой — переходим в deep_research
            DEEP_DOC_THRESHOLD = 20
            if len(briefs) > DEEP_DOC_THRESHOLD or briefs_total > 100_000:
                from app.skills.deep_research import run_deep_research
                logger.info("full-mode: switching to deep_research (%d docs, %d brief chars)",
                            len(briefs), briefs_total)
                context_chunks = _build_context(chunks)
                deep_result = await run_deep_research(
                    query=message,
                    db=db,
                    chunks_context=context_chunks,
                    max_docs=10,
                )
                # Превратим plain dict в FactItem'ы используя index_map
                facts: list[FactItem] = []
                index_map: dict[int, RetrievedChunk] = {i + 1: c for i, c in enumerate(chunks)}
                for f in deep_result.get("facts", []):
                    if not isinstance(f, dict) or not f.get("statement"):
                        continue
                    try:
                        source_num = int(f.get("source_id", 0))
                    except (TypeError, ValueError):
                        source_num = 0
                    chunk = index_map.get(source_num)
                    from uuid import UUID as _UUID
                    if chunk:
                        doc_row = await get_document(db, chunk.document_id)
                        try:
                            doc_uuid = _UUID(str(chunk.document_id))
                        except (TypeError, ValueError):
                            doc_uuid = _UUID("00000000-0000-0000-0000-000000000000")
                        source = SourceRef(
                            document_id=doc_uuid,
                            title=doc_row.title if doc_row else (chunk.title or chunk.document_id),
                            status=chunk.status,  # type: ignore[arg-type]
                            hierarchy_level=chunk.hierarchy_level,
                            section=chunk.section or None,
                            confluence_url=doc_row.confluence_url if doc_row else None,
                        )
                    else:
                        source = SourceRef(
                            document_id=_UUID("00000000-0000-0000-0000-000000000000"),
                            title="Источник не определён",
                            status="unknown",  # type: ignore[arg-type]
                            hierarchy_level=5,
                        )
                    facts.append(FactItem(statement=f["statement"], source=source))

                return {
                    "answer": deep_result.get("answer", ""),
                    "facts": facts,
                    "hypotheses": deep_result.get("hypotheses", []) or [],
                    "warnings": deep_result.get("warnings", []) or [],
                    "requires_verification": deep_result.get("requires_verification", []) or [],
                    "agents_used": ["docs", "deep_research"],
                }

            # Стратегия 2: брифы влезают, тексты — нет
            if briefs:
                parts = [f"=== ОБЗОР ДОКУМЕНТА: {doc.title} (L{doc.hierarchy_level or 5}) ===\n{brief}"
                         for doc, brief in briefs]
                doc_briefs_block = "\n\n".join(parts)
                logger.info("full-mode: corpus too big (%d full chars), using %d briefs (%d chars)",
                            total, len(briefs), briefs_total)

    # Entity memory — обогащаем контекст релевантными сущностями
    entity_block = ""
    if db is not None:
        keywords = [w for w in message.split() if len(w) > 3]
        entities = await search_entities_by_query(db, keywords, limit=20)
        doc_ids = list({c.document_id for c in chunks})
        contradictions_in_scope = await get_open_contradictions_for_docs(db, doc_ids)
        entity_block = _build_entity_memory_block(entities, contradictions_in_scope)

    # Если загружен файл — добавляем его текст к запросу
    extra_context = ""
    if file_content:
        extra_context = f"\n\n[ЗАГРУЖЕННЫЙ ДОКУМЕНТ ДЛЯ АНАЛИЗА]\n{file_content[:4000]}"

    context = _build_context(chunks)
    mode_instruction = MODE_INSTRUCTIONS.get(mode, MODE_INSTRUCTIONS[ChatMode.search])

    if full_texts_block:
        knowledge_section = (
            "\n\nПОЛНЫЕ ТЕКСТЫ ДОКУМЕНТОВ (анализируй ВСЁ что есть, не упускай детали):\n"
            + full_texts_block + "\n"
        )
    elif doc_briefs_block:
        knowledge_section = (
            "\n\nОБЗОРЫ ВСЕХ ДОКУМЕНТОВ В БАЗЕ (для общей картины каждого дока):\n"
            + doc_briefs_block + "\n"
        )
    else:
        knowledge_section = ""

    # История диалога — для follow-up'ов и местоимений
    history_section = ""
    if history:
        lines = []
        for m in list(history)[-6:]:
            role = "User" if m.role == "user" else "Assistant"
            content = (m.content or "").strip()
            if len(content) > 600:
                content = content[:600] + "..."
            lines.append(f"[{role}] {content}")
        if lines:
            history_section = (
                "\n\nИСТОРИЯ ДИАЛОГА (последние сообщения, используй для понимания "
                "контекста и follow-up вопросов):\n" + "\n".join(lines) + "\n"
            )

    # Подсказка по стилю — поверх mode_instruction
    style_hint = {
        "report": "Стиль: длинный markdown-отчёт с разделами H2.",
        "list": "Стиль: компактный список с подзаголовками H3 для группировки.",
        "short": "Стиль: короткий ответ 1-3 абзаца. Без длинных разделов.",
        "plan": "Стиль: пошаговый план — пронумерованный список шагов с описанием.",
        "qa": "Стиль: формат «Вопрос — Ответ» с короткими блоками.",
    }.get(style, "")

    user_message = (
        f"Режим: {mode.value}\n"
        f"Инструкция: {mode_instruction}\n"
        + (f"{style_hint}\n" if style_hint else "")
        + history_section
        + knowledge_section
        + f"\nФРАГМЕНТЫ ДОКУМЕНТОВ (для точных цитат с source_id):\n{context}"
        + (f"\n\n{entity_block}" if entity_block else "")
        + extra_context
        + f"\n\nВОПРОС: {message}"
    )

    # full mode требует длинного markdown-отчёта (1500 слов ≈ 2K tokens) + 20 фактов
    # JSON (~2K tokens). 4096 не хватает — поднимаем до 8000 для full.
    max_tokens = 8000 if mode == ChatMode.full else 4096
    try:
        raw = await call_llm(
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
            max_tokens=max_tokens,
        )
    except Exception as e:
        logger.error("docs_agent: LLM call failed: %s", e)
        return {
            "answer": "",
            "facts": [],
            "hypotheses": [],
            "warnings": [f"⚠️ Ошибка обращения к LLM: {e}"],
            "requires_verification": [],
            "chunks_used": len(chunks),
            "agents_used": ["docs"],
        }

    answer, facts, hypotheses, warnings, requires = await _parse_llm_response(
        raw, chunks, db
    )

    # Self-correction только для full mode: ещё один LLM-вызов критикует ответ,
    # и если есть проблемы — генерим заново с feedback'ом.
    agents = ["docs"]
    if mode == ChatMode.full and chunks:
        try:
            from app.skills.self_check import critique
            payload = {
                "answer": answer,
                "facts": facts,
                "hypotheses": hypotheses,
                "warnings": warnings,
                "requires_verification": requires,
            }
            crit = await critique(message, payload, context)
            if not crit.get("ok", True) and (crit.get("issues") or crit.get("missing_facts")):
                logger.info("self_check: regenerating with %d issues, %d missing",
                            len(crit.get("issues", [])), len(crit.get("missing_facts", [])))
                feedback = (
                    "\n\nКРИТИКА ПРЕДЫДУЩЕЙ ВЕРСИИ ОТВЕТА (исправь эти проблемы):\n"
                    + "\n".join(f"- {i}" for i in crit.get("issues", []))
                    + (
                        "\n\nКЛЮЧЕВЫЕ ФАКТЫ КОТОРЫЕ НУЖНО ДОБАВИТЬ:\n"
                        + "\n".join(f"- {f}" for f in crit.get("missing_facts", []))
                        if crit.get("missing_facts") else ""
                    )
                )
                raw2 = await call_llm(
                    system=SYSTEM_PROMPT,
                    messages=[{"role": "user", "content": user_message + feedback}],
                    max_tokens=max_tokens,
                )
                ans2, facts2, hyp2, warn2, req2 = await _parse_llm_response(raw2, chunks, db)
                # Пере-используем результат если он не "пустой" (защита от регресса)
                if ans2 and len(facts2) >= max(1, len(facts) - 2):
                    answer, facts, hypotheses, warnings, requires = ans2, facts2, hyp2, warn2, req2
                    agents.append("self_check")
        except Exception as exc:
            logger.warning("self_check pipeline error (skipping): %s", exc)

    # Предупреждение если нет чанков
    if not chunks:
        warnings.append("⚠️ Релевантных документов по данному запросу не найдено")

    # Предупреждение об archived чанках
    archive_chunks = {c.document_id: c for c in chunks if c.status == "archived"}
    for doc_id, c in archive_chunks.items():
        label = c.title or doc_id[:8]
        warnings.append(f"⚠️ Использованы данные из архивного документа «{label}»")

    return {
        "answer": answer,
        "facts": facts,
        "hypotheses": hypotheses,
        "warnings": warnings,
        "requires_verification": requires,
        "chunks_used": len(chunks),
        "agents_used": agents,
    }
