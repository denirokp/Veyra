"""Corpus Agent — RAG поиск + LLM генерация с ФАКТ/ГИПОТЕЗА структурой."""
from __future__ import annotations

import json
import re

from sqlalchemy.ext.asyncio import AsyncSession

from app.clients import get_llm
from app.models.schemas import ChatMode, ChatResponse, FactItem, SourceRef
from app.rag.retriever import RetrievedChunk, retrieve
from app.settings import settings
from app.storage.sql_db import (
    get_document,
    get_open_contradictions_for_docs,
    search_entities_by_query,
)

SYSTEM_PROMPT = """\
Ты аналитик корпоративной памяти команды Avito. У тебя есть доступ к корпусу \
внутренних документов — стратегий, ресёрчей, операционных планов.

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
        "Найди и синтезируй всё что знает корпус по заданной теме. "
        "ОБЯЗАТЕЛЬНО: после прямого ответа добавь в requires_verification "
        "что НЕ учитывается в текущих планах, какие факторы влияния упущены, "
        "где есть риск расхождения между планом и реальностью. "
        "Если видишь документы которые противоречат друг другу — отметь в warnings."
    ),
    ChatMode.contradictions: (
        "Найди числовые расхождения по теме. "
        "В facts укажи разные цифры из разных документов. "
        "В warnings — явно отметь каждое расхождение."
    ),
    ChatMode.promises: (
        "Найди все обещания и планы по теме. "
        "Для каждого: точная цитата, документ, срок если есть. "
        "В warnings — отметь просроченные или без дедлайна."
    ),
    ChatMode.gaps: (
        "Найди темы которые обсуждались в корпусе но не вошли в текущую стратегию. "
        "Ранжируй по недавности и количеству упоминаний."
    ),
    ChatMode.write: (
        "Ты помогаешь написать документ. "
        "Собери все релевантные факты из корпуса для использования в тексте."
    ),
    ChatMode.validate: (
        "Оцени инициативу на основе корпуса. "
        "Укажи: что уже изучали, что противоречит, что поддерживает. "
        "В requires_verification — конкретные вопросы которые нужно проверить перед запуском."
    ),
    ChatMode.research: (
        "Собери всё что корпус знает по теме включая архивные документы. "
        "Ищи паттерны, тренды, повторяющиеся проблемы. "
        "В hypotheses — что можно предположить исходя из найденного."
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

    lines = ["[ENTITY MEMORY — известные факты из корпуса]"]

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
            data = json.loads(match.group())
        else:
            return raw, [], [], ["⚠️ Не удалось разобрать структурированный ответ"], []

    answer = data.get("answer", "")
    hypotheses = data.get("hypotheses", [])
    warnings = data.get("warnings", [])
    requires = data.get("requires_verification", [])

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
            source = SourceRef(
                document_id=chunk.document_id,  # type: ignore[arg-type]
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
    # Поиск релевантных чанков
    include_archive = mode in (ChatMode.search, ChatMode.gaps, ChatMode.contradictions)
    chunks = await retrieve(message, top_k=15, include_archive=include_archive)

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

    user_message = (
        f"Режим: {mode.value}\n"
        f"Инструкция: {mode_instruction}\n\n"
        f"КОРПУС ДОКУМЕНТОВ:\n{context}"
        + (f"\n\n{entity_block}" if entity_block else "")
        + extra_context
        + f"\n\nВОПРОС: {message}"
    )

    llm = get_llm()
    response = await llm.messages.create(
        model=settings.LLM_MODEL,
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}],
    )
    raw = response.content[0].text.strip()

    answer, facts, hypotheses, warnings, requires = await _parse_llm_response(
        raw, chunks, db
    )

    # Предупреждение если нет чанков
    if not chunks:
        warnings.append("⚠️ В корпусе не найдено релевантных документов по данному запросу")

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
        "agents_used": ["corpus"],
    }
