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

source_id — это НОМЕР источника (1, 2, 3...) из заголовка [Источник N] в контексте выше.\


Если в предоставленных фрагментах встречаются разные значения одной метрики — \
обязательно отметь обе цифры в warnings с указанием источника каждой.

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
        "Сделай МАКСИМАЛЬНО ПОДРОБНЫЙ разбор по теме. Это главный режим — "
        "пользователь хочет всю картину, а не краткое summary.\n\n"
        "У ТЕБЯ ДВА ИСТОЧНИКА КОНТЕКСТА:\n"
        "(А) ОБЗОРЫ ВСЕХ ДОКУМЕНТОВ — компактные структурированные саммари "
        "каждого документа целиком. Используй их чтобы видеть общую картину "
        "каждого документа, понять структуру инициатив, найти владельцев, "
        "сроки, цифры из таблиц.\n"
        "(Б) ФРАГМЕНТЫ ДОКУМЕНТОВ — точные куски с source_id. Используй для "
        "цитирования: каждый факт в JSON должен ссылаться на source_id из (Б).\n\n"
        "ЖЁСТКИЕ ТРЕБОВАНИЯ:\n"
        "1. answer (4-7 предложений): суть, статус, ключевые цифры с единицами, "
        "временные горизонты. Опирайся на (А) для картины. НЕ повторяй то что "
        "будет в facts.\n"
        "2. facts: МИНИМУМ 10-15 фактов. ПО КАЖДОМУ документу обязательно "
        "минимум 3-5 фактов. Используй цифры/имена из (А), цитату из (Б). "
        "Каждый факт сопровождай source_id из (Б).\n"
        "3. warnings: расхождения между документами, риски (если в обзорах "
        "указаны probability/impact — выписывай), просроченные/без-владельца.\n"
        "4. hypotheses: рыночный контекст, аналоги конкурентов из (А), "
        "твои предположения с disclaimer.\n"
        "5. requires_verification: что не закрыто планами, какие owners/deadlines "
        "не назначены, что критично проверить.\n\n"
        "НЕ округляй цифры. НЕ выдумывай. Если факт есть только в (А) но нет "
        "в (Б) — можешь упомянуть в answer/warnings/hypotheses, но НЕ в facts "
        "(facts требует source_id из фрагментов)."
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

    def _as_str_list(raw):
        # LLM иногда возвращает элементы как dict {statement, source_id} —
        # схема ждёт строки, приводим вручную.
        out = []
        for w in raw or []:
            if not w:
                continue
            if isinstance(w, str):
                out.append(w)
            elif isinstance(w, dict):
                out.append(w.get("statement") or w.get("text") or str(w))
            else:
                out.append(str(w))
        return out

    answer = data.get("answer", "")
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
) -> dict:
    # Поиск релевантных чанков — для full режима берём больше материала,
    # чтобы LLM мог достать конкретные числа и атрибуцию.
    include_archive = mode in (ChatMode.search, ChatMode.gaps, ChatMode.contradictions)
    top_k = 30 if mode == ChatMode.full else 15
    chunks = await retrieve(message, top_k=top_k, include_archive=include_archive)

    # Document-level контекст: для full режима подгружаем брифы ВСЕХ актуальных
    # документов целиком — чтобы LLM видел картину каждого дока, а не только
    # retrieve-фрагменты. Это и есть document-level анализ.
    doc_briefs_block = ""
    if mode == ChatMode.full and db is not None:
        from app.storage.sql_db import get_all_document_briefs
        briefs = await get_all_document_briefs(db, statuses=["actual"], limit=20)
        if briefs:
            parts = [f"=== ОБЗОР ДОКУМЕНТА: {doc.title} (L{doc.hierarchy_level or 5}) ===\n{brief}"
                     for doc, brief in briefs]
            doc_briefs_block = "\n\n".join(parts)

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

    briefs_section = (
        f"\n\nОБЗОРЫ ВСЕХ ДОКУМЕНТОВ В БАЗЕ (для общей картины каждого дока):\n{doc_briefs_block}\n"
        if doc_briefs_block else ""
    )

    user_message = (
        f"Режим: {mode.value}\n"
        f"Инструкция: {mode_instruction}\n"
        + briefs_section
        + f"\nФРАГМЕНТЫ ДОКУМЕНТОВ (для точных цитат с source_id):\n{context}"
        + (f"\n\n{entity_block}" if entity_block else "")
        + extra_context
        + f"\n\nВОПРОС: {message}"
    )

    try:
        raw = await call_llm(
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
            max_tokens=4096,
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
        "agents_used": ["docs"],
    }
