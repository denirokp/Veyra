"""Orchestrator — анализ запроса, роутинг к агентам, синтез финального ответа."""
from __future__ import annotations

import base64
import json
import logging
import re
import time
import uuid as _uuid
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents import docs as docs_agent
from app.clients import call_llm
from uuid import UUID

logger = logging.getLogger(__name__)

from app.models.schemas import ChatMode, ChatRequest, ChatResponse, FactItem, SourceRef


# Поддерживаемые стили вывода. Влияют на тон и формат answer, не на pipeline.
OUTPUT_STYLES = ("report", "list", "short", "plan", "qa")
DEFAULT_STYLE = "report"


@dataclass
class Intent:
    mode: ChatMode
    style: str  # report | list | short | plan | qa


_CLASSIFIER_PROMPT = """\
Ты — диспетчер запросов к корпоративной базе знаний. На входе:
- ПОСЛЕДНИЕ СООБЩЕНИЯ из диалога (могут быть пустыми если новый чат)
- ТЕКУЩИЙ ЗАПРОС пользователя

Твоя задача — определить (1) РЕЖИМ и (2) СТИЛЬ ответа.

РЕЖИМЫ:
- search: точечный поиск конкретного факта («что мы знаем про X», «когда запустили Y»)
- contradictions: расхождения, конфликты в данных
- promises: планы, дедлайны, что обещали
- gaps: что упущено, серые зоны, риски не закрытые
- write: создание текста («напиши», «составь», «подготовь черновик»)
- validate: оценка инициативы/идеи целиком («оцени», «проверь идею»)
- research: конкуренты, рынок, бенчмарки, best practices
- full: полный разбор / синтез из нескольких источников / совет+план на основе данных

СТИЛИ:
- report: длинный markdown-отчёт с секциями (для глубокого анализа)
- list: структурированный список с подзаголовками (для обзоров и описей)
- short: короткий ответ 1-3 абзаца (для конкретных вопросов)
- plan: пошаговый план/чеклист (для actionable задач)
- qa: формат «вопрос-ответ» (для пояснений и FAQ-стиля)

Используй контекст диалога:
- если запрос продолжает обсуждение («теперь напиши план», «уточни X», «а что насчёт Y») — \
учитывай предыдущую тему
- короткие follow-up'ы обычно требуют короткого стиля (short/list/plan)
- свежий запрос про синтез нескольких документов → full+report
- "напиши план" после анализа → write+plan
- "уточни" / "а что про X" → search+short

Ответь СТРОГО JSON: {"mode": "<режим>", "style": "<стиль>"}.
Без markdown, без объяснений.\
"""


# Триггеры эвристического upgrade search → full (синтез + рекомендация)
_ADVISORY_TRIGGERS = (
    "как выстро", "как улучш", "как мы можем", "как нам", "как сделать",
    "помоги построить", "помоги составить", "помоги разработать",
    "какой подход", "какую стратегию", "исходя из", "опираясь на",
    "возьми опыт", "возьми также опыт", "best practices", "бенчмарк",
    "как делают", "рекоменд",
)


def _format_history(messages) -> str:
    """Форматирует историю в компактный текстовый блок для промпта."""
    if not messages:
        return "(новый диалог, истории нет)"
    parts = []
    for m in messages:
        role = "User" if m.role == "user" else "Assistant"
        # Обрезаем длинные ответы — для классификатора важна тема, не объём
        snippet = (m.content or "").strip()
        if len(snippet) > 400:
            snippet = snippet[:400] + "..."
        parts.append(f"[{role}] {snippet}")
    return "\n".join(parts)


async def detect_intent(message: str, history) -> Intent:
    """Определяет (mode, style) по запросу + последним сообщениям диалога."""
    user_msg = (
        f"=== Последние сообщения диалога ===\n{_format_history(history)}\n\n"
        f"=== Текущий запрос ===\n{message}"
    )
    try:
        raw = await call_llm(
            system=_CLASSIFIER_PROMPT,
            messages=[{"role": "user", "content": user_msg}],
            max_tokens=80,
        )
    except Exception as e:
        logger.warning("detect_intent failed, falling back to search/report: %s", e)
        return Intent(mode=ChatMode.search, style=DEFAULT_STYLE)

    raw = raw.strip()
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
        logger.warning("detect_intent: cant parse %r, fallback", raw[:100])
        return Intent(mode=ChatMode.search, style=DEFAULT_STYLE)

    mode_raw = (parsed.get("mode") or "").strip().lower()
    style_raw = (parsed.get("style") or DEFAULT_STYLE).strip().lower()
    try:
        mode = ChatMode(mode_raw)
    except ValueError:
        mode = ChatMode.search
    if style_raw not in OUTPUT_STYLES:
        style_raw = DEFAULT_STYLE

    # Эвристический upgrade search → full на advisory-вопросах
    if mode == ChatMode.search:
        msg_lc = message.lower()
        if any(t in msg_lc for t in _ADVISORY_TRIGGERS):
            logger.info("detect_intent: upgrading search → full (advisory)")
            mode = ChatMode.full
            if style_raw == "short":
                style_raw = DEFAULT_STYLE

    # Follow-up короткий — переопределяем стиль на short. «А что насчёт X?»,
    # «уточни», «подробнее» после большого отчёта не должны генерить ещё один
    # большой отчёт.
    msg_norm = message.strip()
    if history and msg_norm and len(msg_norm) < 80:
        last_assistant = next(
            (m for m in reversed(history) if m.role == "assistant"),
            None,
        )
        followup_markers = (
            "а ", "и ", "также", "уточни", "подробнее", "детальнее",
            "что насчёт", "что насчет", "почему", "когда", "сколько",
            "теперь", "далее",
        )
        starts_followup = any(msg_norm.lower().startswith(t) for t in followup_markers)
        if last_assistant and (starts_followup or len(msg_norm) < 40):
            if mode == ChatMode.full:
                # Не делаем full-отчёт на «а что насчёт X?» — это search
                mode = ChatMode.search
            if style_raw == "report":
                style_raw = "short"
            logger.info("detect_intent: follow-up shortcut → mode=%s, style=%s",
                        mode.value, style_raw)

    return Intent(mode=mode, style=style_raw)


def _decode_file(file_b64: str) -> str:
    try:
        return base64.b64decode(file_b64).decode("utf-8", errors="replace")
    except Exception:
        return ""


async def _run_validate(message: str, db: AsyncSession) -> dict:
    """Роутит validate-запрос в initiative_review."""
    from app.skills.initiative_review import run_initiative_review

    lines = message.strip().splitlines()
    title = lines[0].strip() if lines else message[:80]
    body = "\n".join(lines[1:]).strip() if len(lines) > 1 else message

    review = await run_initiative_review(title, body, db)
    verdict = review.get("recommendation", {}).get("verdict", "needs_work")
    reasoning = review.get("recommendation", {}).get("reasoning", "")
    verdict_ru = {"approve": "Одобрить", "needs_work": "Требует доработки", "reject": "Отклонить"}
    answer = f"**{verdict_ru.get(verdict, verdict)}**: {reasoning}"

    # initiative_review.strategic_anchors содержит реальные doc_id из RAG
    # — используем их, чтобы факты были кликабельны и привязаны к нужному
    # документу, а не к синтетическому nil-UUID.
    facts: list[FactItem] = []
    for anchor in review.get("strategic_anchors", [])[:5]:
        anchor_doc_id = anchor.get("document_id", "")
        try:
            doc_uuid = UUID(str(anchor_doc_id))
        except (TypeError, ValueError):
            doc_uuid = UUID("00000000-0000-0000-0000-000000000000")
        facts.append(FactItem(
            statement=f"{anchor['title']}: {anchor['relevance']}",
            source=SourceRef(
                document_id=doc_uuid,
                title=anchor["title"],
                status=anchor.get("status", "actual"),  # type: ignore[arg-type]
                hierarchy_level=int(anchor.get("hierarchy_level", 2)),
            ),
        ))

    warnings = [c["description"] for c in review.get("conflicts", [])[:5]]
    gaps = [f"Не хватает ({g['gap_type']}): {g['description']}" for g in review.get("gaps", [])[:5]]

    return {
        "answer": answer,
        "facts": facts,
        "hypotheses": [a["lesson"] for a in review.get("analogues", [])[:3]],
        "warnings": warnings,
        "requires_verification": gaps,
        "chunks_used": review.get("metadata", {}).get("chunks_used", 0),
        "agents_used": ["docs", "initiative_review", "market_agent"],
    }


async def run(request: ChatRequest, db: AsyncSession) -> ChatResponse:
    t0 = time.monotonic()

    # 1. Загружаем последние сообщения этой сессии — для контекстной памяти
    from app.storage.sql_db import get_recent_chat_messages, save_chat_message
    session_id_str = str(request.session_id) if request.session_id else ""
    history = await get_recent_chat_messages(db, session_id_str, limit=8) if session_id_str else []

    # 2. Определяем (mode, style). Если пользователь явно указал mode — стиль
    # подбираем сами; иначе классификатор выбирает оба.
    if request.mode is not None:
        # Юзер форсит режим через UI-пилюлю — стиль ставим дефолтный по моду
        forced_mode = request.mode
        forced_style = {
            ChatMode.write: "plan",
            ChatMode.search: "short",
            ChatMode.full: "report",
            ChatMode.validate: "report",
            ChatMode.gaps: "list",
            ChatMode.contradictions: "list",
            ChatMode.promises: "list",
            ChatMode.research: "report",
        }.get(forced_mode, DEFAULT_STYLE)
        intent = Intent(mode=forced_mode, style=forced_style)
    else:
        intent = await detect_intent(request.message, history)
        logger.info("intent: mode=%s, style=%s", intent.mode.value, intent.style)

    file_content = _decode_file(request.file) if request.file else None

    # 3. Маршрутизируем в нужный pipeline
    if intent.mode == ChatMode.validate:
        result = await _run_validate(request.message, db)
    else:
        result = await docs_agent.run(
            message=request.message,
            mode=intent.mode,
            file_content=file_content,
            db=db,
            history=history,
            style=intent.style,
        )

    latency_ms = int((time.monotonic() - t0) * 1000)

    response = ChatResponse(
        answer=result["answer"],
        facts=result["facts"],
        hypotheses=result["hypotheses"],
        warnings=result["warnings"],
        requires_verification=result["requires_verification"],
        metadata={
            "mode_detected": intent.mode.value,
            "style": intent.style,
            "agents_used": result.get("agents_used", ["docs"]),
            "latency_ms": latency_ms,
            "chunks_retrieved": result.get("chunks_used", 0),
        },
    )

    # 4. Сохраняем оба сообщения в историю для будущих обращений
    if session_id_str:
        try:
            await save_chat_message(
                db,
                message_id=str(_uuid.uuid4()),
                session_id=session_id_str,
                role="user",
                content=request.message,
            )
            # Для assistant сохраняем JSON ответа (на случай отображения архива)
            await save_chat_message(
                db,
                message_id=str(_uuid.uuid4()),
                session_id=session_id_str,
                role="assistant",
                content=response.answer,
                mode=intent.mode.value,
                response_json=response.model_dump_json(),
            )
        except Exception as exc:
            logger.warning("failed to persist chat messages: %s", exc)

    return response
