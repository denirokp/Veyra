"""Orchestrator — анализ запроса, роутинг к агентам, синтез финального ответа."""
from __future__ import annotations

import base64
import logging
import time

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents import docs as docs_agent
from app.clients import call_llm
from uuid import UUID

logger = logging.getLogger(__name__)

from app.models.schemas import ChatMode, ChatRequest, ChatResponse, FactItem, SourceRef

_MODE_CLASSIFIER_PROMPT = """\
Определи режим обработки запроса пользователя к корпоративной базе знаний.

Режимы:
- search: точечный поиск конкретного факта в документах \
(«что мы знаем про X», «когда запустили Y», «сколько у нас Z»)
- contradictions: пользователь ищет расхождения, конфликты или несоответствия в данных \
(«две разные цифры», «не сходится», «кто прав», «разные версии», «противоречие»)
- promises: пользователь спрашивает о планах, обещаниях, дедлайнах, что должно быть сделано \
(«что планировали», «P0-задачи», «дедлайны», «что обещали», «что не сделали»)
- gaps: пользователь ищет пробелы, слепые пятна, что упущено или не учтено \
(«что не учли», «чего не хватает», «что пропустили», «какие риски не закрыты»)
- write: пользователь просит написать или подготовить документ, тезисы, записку, абзац \
(«напиши», «составь», «подготовь»)
- validate: пользователь просит оценить чью-то инициативу/идею/предложение целиком \
(«оцени», «стоит ли», «что думаешь об инициативе», «проверь идею»)
- research: пользователь спрашивает о конкурентах, рынке, внешнем контексте \
(«как делают другие», «best practices», «опыт из вне», «бенчмарк»)
- full: пользователь хочет ПОЛНЫЙ разбор или СИНТЕЗ ИЗ НЕСКОЛЬКИХ ИСТОЧНИКОВ или \
просит ПРАКТИЧЕСКИЙ СОВЕТ/ПЛАН на основе данных \
(«разбери всё», «дай полный анализ», «комплексно по теме», «расскажи всё», \
«как выстроить», «как улучшить», «как мы можем», «помоги построить», \
«какой подход выбрать», «исходя из X и Y предложи», «опираясь на ... возьми ещё ...»)

ВАЖНО: если запрос требует ОДНОВРЕМЕННО (а) данных из документов и (б) рекомендаций/плана \
ИЛИ комбинирует несколько источников — выбирай full, а не search.

Ответь ОДНИМ словом — именем режима. Без пояснений.\
"""


# Триггеры на которые мы апгрейдим mode до full (синтез + рекомендация).
# LLM-классификатор иногда ставит "search" даже на явно синтетические вопросы
# («как выстроить онбординг исходя из X и опыта Y»), для которых search-режим
# даёт слабый ответ.
_ADVISORY_TRIGGERS = (
    "как выстро", "как улучш", "как мы можем", "как нам", "как сделать",
    "помоги построить", "помоги составить", "помоги разработать",
    "какой подход", "какую стратегию", "исходя из", "опираясь на",
    "возьми опыт", "возьми также опыт", "best practices", "бенчмарк",
    "как делают", "рекоменд",
)


async def detect_mode(message: str) -> ChatMode:
    try:
        raw = await call_llm(
            system=_MODE_CLASSIFIER_PROMPT,
            messages=[{"role": "user", "content": message}],
            max_tokens=10,
        )
        mode = ChatMode(raw.strip().lower())
    except Exception as e:
        logger.warning("detect_mode fallback to search: %s", e)
        return ChatMode.search

    # Эвристический upgrade: если классификатор выбрал search, но запрос
    # содержит «как выстроить / помоги составить / опираясь на ...» —
    # это синтез + рекомендация, а не точечный поиск. Поднимаем до full.
    if mode == ChatMode.search:
        msg_lc = message.lower()
        if any(t in msg_lc for t in _ADVISORY_TRIGGERS):
            logger.info("detect_mode: upgrading search → full (advisory query)")
            return ChatMode.full

    return mode


def _decode_file(file_b64: str) -> str:
    try:
        return base64.b64decode(file_b64).decode("utf-8", errors="replace")
    except Exception:
        return ""


async def _run_validate(message: str, db: AsyncSession) -> dict:
    """Роутит validate-запрос в initiative_review и формирует ChatResponse-совместимый dict."""
    from app.skills.initiative_review import run_initiative_review

    # Первая строка = заголовок инициативы, остальное = текст
    lines = message.strip().splitlines()
    title = lines[0].strip() if lines else message[:80]
    body = "\n".join(lines[1:]).strip() if len(lines) > 1 else message

    review = await run_initiative_review(title, body, db)

    verdict = review.get("recommendation", {}).get("verdict", "needs_work")
    reasoning = review.get("recommendation", {}).get("reasoning", "")

    verdict_ru = {"approve": "Одобрить", "needs_work": "Требует доработки", "reject": "Отклонить"}
    answer = f"**{verdict_ru.get(verdict, verdict)}**: {reasoning}"

    facts: list[FactItem] = []
    for anchor in review.get("strategic_anchors", [])[:5]:
        facts.append(FactItem(
            statement=f"{anchor['title']}: {anchor['relevance']}",
            source=SourceRef(
                document_id=UUID("00000000-0000-0000-0000-000000000000"),
                title=anchor["title"],
                status="actual",  # type: ignore[arg-type]
                hierarchy_level=2,
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

    mode = request.mode or await detect_mode(request.message)
    file_content = _decode_file(request.file) if request.file else None

    # validate → initiative_review
    if mode == ChatMode.validate:
        result = await _run_validate(request.message, db)
    else:
        result = await docs_agent.run(
            message=request.message,
            mode=mode,
            file_content=file_content,
            db=db,
        )

    latency_ms = int((time.monotonic() - t0) * 1000)

    return ChatResponse(
        answer=result["answer"],
        facts=result["facts"],
        hypotheses=result["hypotheses"],
        warnings=result["warnings"],
        requires_verification=result["requires_verification"],
        metadata={
            "mode_detected": mode.value,
            "agents_used": result.get("agents_used", ["docs"]),
            "latency_ms": latency_ms,
            "chunks_retrieved": result.get("chunks_used", 0),
        },
    )
