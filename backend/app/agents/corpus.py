"""Corpus Agent — RAG поиск + LLM генерация с ФАКТ/ГИПОТЕЗА структурой.

Оркестрация — tool-use loop: модель сама решает, нужен ли дополнительный
поиск по корпусу (search_corpus) или рыночный контекст (market_context),
вместо жёсткого single-shot RAG.
"""
from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.clients import get_llm
from app.models.schemas import ChatMode, FactItem, SourceRef
from app.rag.retriever import RetrievedChunk, fuse_results, retrieve
from app.settings import settings
from app.skills.market_agent import get_market_context
from app.storage.sql_db import (
    get_document,
    get_open_contradictions_for_docs,
    list_contradictions,
    search_entities_by_query,
)

_PROMPTS_DIR = Path(__file__).parent.parent.parent / "prompts"
SYSTEM_PROMPT = (_PROMPTS_DIR / "corpus_system.txt").read_text(encoding="utf-8").strip()

_MAX_TOOL_ITERATIONS = 5

_INJECTION_PATTERNS = re.compile(
    r"ignore\s+(?:previous|all)\s+instructions?"
    r"|игнорируй\s+(?:предыдущие|все)\s+инструкции"
    r"|forget\s+everything"
    r"|забудь\s+всё"
    r"|you\s+are\s+now\s+(?:a\s+)?(?:an?\s+)?\w+"
    r"|ты\s+теперь\s+\w+"
    r"|act\s+as\s+(?:a\s+)?(?:an?\s+)?\w+"
    r"|действуй\s+как\s+\w+"
    r"|system\s+prompt"
    r"|системный\s+промпт"
    r"|<\s*/?system\s*>",
    re.IGNORECASE,
)

MODE_INSTRUCTIONS: dict[ChatMode, str] = {
    ChatMode.search: (
        "Найди и синтезируй всё что знает корпус по заданной теме. "
        "Если видишь документы которые противоречат друг другу — отметь в warnings. "
        "requires_verification оставь пустым массивом."
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

# Инструменты, доступные агенту в tool-use loop.
_TOOLS = [
    {
        "name": "search_corpus",
        "description": (
            "Поиск по корпусу внутренних документов команды (гибридный retrieval: "
            "vector + BM25 + RRF). Используй, когда предоставленных источников "
            "недостаточно: нужно уточнить тему, проверить смежный вопрос или найти "
            "конкретную метрику. Возвращает пронумерованные источники — ссылайся на "
            "их номера в поле source_id финального ответа."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Поисковый запрос"},
                "include_archive": {
                    "type": "boolean",
                    "description": "Включать архивные документы (по умолчанию false)",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "market_context",
        "description": (
            "Рыночный контекст по теме на основе общих знаний модели — это НЕ "
            "данные компании. Результат всегда гипотеза, требующая верификации. "
            "Используй, только если вопрос явно требует внешнего/рыночного взгляда."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "topic": {"type": "string", "description": "Тема для рыночного контекста"},
            },
            "required": ["topic"],
        },
    },
]


def _build_context(chunks: list[RetrievedChunk], offset: int = 0) -> str:
    """Рендерит чанки как пронумерованные источники.

    offset — глобальный сдвиг нумерации (источники, добавленные через
    search_corpus, продолжают сквозную нумерацию реестра)."""
    parts = []
    for i, c in enumerate(chunks):
        status_label = c.status.upper()
        level_label = f"L{c.hierarchy_level}"
        title = c.title or c.document_id[:8]
        section = f" / {c.section}" if c.section else ""
        parts.append(
            f"[Источник {offset + i + 1} | {title}{section} | {status_label} | {level_label}]\n"
            f"{c.content}"
        )
    return "\n\n---\n\n".join(parts)


def _wrap_uploaded_content(raw: str, max_chars: int = 4000) -> tuple[str, str]:
    """Оборачивает содержимое загруженного файла в XML-тег и проверяет на инъекции.

    Возвращает (wrapped_text, warning_message).
    warning_message пустой если инъекций не обнаружено.
    """
    truncated = raw[:max_chars]
    warning = ""
    if _INJECTION_PATTERNS.search(truncated):
        warning = "⚠️ Загруженный документ содержит потенциальные инструкции — они проигнорированы"
    return f"<uploaded_document>\n{truncated}\n</uploaded_document>", warning


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


async def _dispatch_tool(
    name: str,
    tool_input: dict,
    registry: list[RetrievedChunk],
) -> str:
    """Исполняет вызов инструмента. registry мутируется — новые (не дублирующие)
    чанки из search_corpus дописываются в конец со сквозной нумерацией."""
    if name == "search_corpus":
        query = str(tool_input.get("query", "")).strip()
        if not query:
            return "Пустой запрос — нечего искать."
        include_archive = bool(tool_input.get("include_archive", False))
        found = await retrieve(query, top_k=10, include_archive=include_archive)
        if not found:
            return f"По запросу «{query}» в корпусе ничего не найдено."
        known_ids = {c.id for c in registry}
        fresh = [c for c in found if c.id not in known_ids]
        if not fresh:
            return f"По запросу «{query}» новых фрагментов нет — всё уже в контексте выше."
        offset = len(registry)
        registry.extend(fresh)
        return _build_context(fresh, offset=offset)

    if name == "market_context":
        topic = str(tool_input.get("topic", "")).strip()
        ctx = await get_market_context(topic)
        return json.dumps(ctx, ensure_ascii=False)

    return f"Неизвестный инструмент: {name}"


async def _run_agent_loop(
    system: str,
    first_user_message: str,
    registry: list[RetrievedChunk],
) -> tuple[str, list[str], set[str]]:
    """Tool-use loop. Модель вызывает инструменты, пока не сформирует финальный
    ответ либо пока не исчерпан лимит итераций. Возвращает
    (raw_text, warnings, tools_used). registry мутируется внутри _dispatch_tool."""
    llm = get_llm()
    messages: list[dict] = [{"role": "user", "content": first_user_message}]
    tools_used: set[str] = set()
    final_text = ""

    for _ in range(_MAX_TOOL_ITERATIONS):
        response = await llm.messages.create(
            model=settings.LLM_MODEL,
            max_tokens=4096,
            system=system,
            tools=_TOOLS,
            messages=messages,
        )

        if response.stop_reason != "tool_use":
            final_text = "\n".join(
                b.text for b in response.content if b.type == "text"
            ).strip()
            break

        messages.append({"role": "assistant", "content": response.content})
        tool_results = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            tools_used.add(block.name)
            result_text = await _dispatch_tool(block.name, block.input, registry)
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": result_text,
            })
        messages.append({"role": "user", "content": tool_results})
    else:
        # Лимит итераций исчерпан — tool_choice=none форсирует текстовый ответ.
        # tools оставляем: история содержит tool_use-блоки и требует их объявления.
        response = await llm.messages.create(
            model=settings.LLM_MODEL,
            max_tokens=4096,
            system=system,
            tools=_TOOLS,
            tool_choice={"type": "none"},
            messages=messages,
        )
        final_text = "\n".join(
            b.text for b in response.content if b.type == "text"
        ).strip()

    warnings: list[str] = []
    if "market_context" in tools_used:
        warnings.append(
            "⚠️ Использован рыночный контекст — гипотеза модели, требует проверки"
        )
    return final_text, warnings, tools_used


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
            source = SourceRef(
                document_id=UUID("00000000-0000-0000-0000-000000000000"),
                title="Источник не определён",
                status="unknown",  # type: ignore[arg-type]
                hierarchy_level=5,
            )

        facts.append(FactItem(statement=f["statement"], source=source))

    return answer, facts, hypotheses, warnings, requires


async def run(
    message: str,
    mode: ChatMode,
    subqueries: list[str] | None = None,
    file_content: str | None = None,
    db: AsyncSession | None = None,
) -> dict:
    # Первичный retrieval по подзапросам → RRF fusion. Реестр источников
    # дальше пополняется агентом через инструмент search_corpus.
    include_archive = mode in (ChatMode.search, ChatMode.gaps, ChatMode.contradictions)
    queries = subqueries or [message]
    if len(queries) == 1:
        initial = await retrieve(queries[0], top_k=15, include_archive=include_archive)
    else:
        results = await asyncio.gather(*[
            retrieve(q, top_k=10, include_archive=include_archive)
            for q in queries
        ])
        initial = fuse_results(*results, top_k=15)

    registry: list[RetrievedChunk] = list(initial)

    # Entity memory — обогащаем контекст релевантными сущностями
    entity_block = ""
    if db is not None:
        keywords = [w for w in message.split() if len(w) > 3]
        entities = await search_entities_by_query(db, keywords, limit=20)
        doc_ids = list({c.document_id for c in registry})
        contradictions_in_scope = await get_open_contradictions_for_docs(db, doc_ids)
        entity_block = _build_entity_memory_block(entities, contradictions_in_scope)

    # Для contradictions режима — дополняем все открытые расхождения из БД
    stored_contradictions_block = ""
    if mode == ChatMode.contradictions and db is not None:
        all_open = await list_contradictions(db, status="open")
        if all_open:
            lines = ["[ЗАФИКСИРОВАННЫЕ ЧИСЛОВЫЕ РАСХОЖДЕНИЯ ИЗ ПАМЯТИ СИСТЕМЫ]"]
            for c in all_open[:10]:
                lines.append(
                    f"  • {c.metric}: {c.value_a} vs {c.value_b}"
                    + (f" (период: {c.period})" if c.period else "")
                )
            stored_contradictions_block = "\n".join(lines)

    extra_context = ""
    extra_warnings: list[str] = []
    if file_content:
        wrapped, inj_warning = _wrap_uploaded_content(file_content)
        extra_context = f"\n\n{wrapped}"
        if inj_warning:
            extra_warnings.append(inj_warning)

    context = _build_context(registry)
    mode_instruction = MODE_INSTRUCTIONS.get(mode, MODE_INSTRUCTIONS[ChatMode.search])

    first_user_message = (
        f"Режим: {mode.value}\n"
        f"Инструкция: {mode_instruction}\n\n"
        f"КОРПУС ДОКУМЕНТОВ:\n{context}"
        + (f"\n\n{entity_block}" if entity_block else "")
        + (f"\n\n{stored_contradictions_block}" if stored_contradictions_block else "")
        + extra_context
        + f"\n\nВОПРОС: {message}\n\n"
        "Если предоставленных источников недостаточно для точного ответа — "
        "вызови инструмент search_corpus. Когда контекста достаточно — "
        "ответь строго в формате JSON."
    )

    raw, tool_warnings, tools_used = await _run_agent_loop(
        SYSTEM_PROMPT, first_user_message, registry
    )

    answer, facts, hypotheses, warnings, requires = await _parse_llm_response(
        raw, registry, db
    )

    warnings.extend(extra_warnings)
    warnings.extend(tool_warnings)

    if not registry:
        warnings.append("⚠️ В корпусе не найдено релевантных документов по данному запросу")

    # Предупреждение об archived чанках
    archive_chunks = {c.document_id: c for c in registry if c.status == "archived"}
    for doc_id, c in archive_chunks.items():
        label = c.title or doc_id[:8]
        warnings.append(f"⚠️ Использованы данные из архивного документа «{label}»")

    # requires_verification показываем только в gaps-режиме
    if mode != ChatMode.gaps:
        requires = []

    agents_used = ["corpus"]
    if "market_context" in tools_used:
        agents_used.append("market_agent")

    return {
        "answer": answer,
        "facts": facts,
        "hypotheses": hypotheses,
        "warnings": warnings,
        "requires_verification": requires,
        "chunks_used": len(registry),
        "agents_used": agents_used,
    }
