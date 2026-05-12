"""Orchestrator — анализ запроса, роутинг к агентам, синтез финального ответа."""
from __future__ import annotations

import base64
import json
import time
from pathlib import Path
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents import corpus as corpus_agent
from app.clients import get_llm
from app.models.schemas import ChatMode, ChatRequest, ChatResponse, FactItem, SourceRef
from app.settings import settings

_PROMPTS_DIR = Path(__file__).parent.parent.parent / "prompts"
_ROUTER_PROMPT = (_PROMPTS_DIR / "router.txt").read_text(encoding="utf-8").strip()


async def route_request(message: str) -> tuple[ChatMode, list[str]]:
    """Один LLM-вызов: определяет режим и декомпозирует запрос на подзапросы."""
    try:
        llm = get_llm()
        response = await llm.messages.create(
            model=settings.LLM_MODEL,
            max_tokens=200,
            system=_ROUTER_PROMPT,
            messages=[{"role": "user", "content": message}],
        )
        data = json.loads(response.content[0].text.strip())
        mode = ChatMode(data.get("mode", "search"))
        subqueries = data.get("subqueries", [message])
        if not isinstance(subqueries, list) or not subqueries:
            subqueries = [message]
        return mode, [str(q) for q in subqueries[:3]]
    except Exception:
        return ChatMode.search, [message]


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
        "agents_used": ["corpus", "initiative_review", "market_agent"],
    }


async def run(request: ChatRequest, db: AsyncSession) -> ChatResponse:
    t0 = time.monotonic()

    file_content = _decode_file(request.file) if request.file else None

    if request.mode:
        mode, subqueries = request.mode, [request.message]
    else:
        mode, subqueries = await route_request(request.message)

    # validate → initiative_review (без декомпозиции)
    if mode == ChatMode.validate:
        result = await _run_validate(request.message, db)
    else:
        result = await corpus_agent.run(
            message=request.message,
            mode=mode,
            subqueries=subqueries,
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
            "agents_used": result.get("agents_used", ["corpus"]),
            "latency_ms": latency_ms,
            "chunks_retrieved": result.get("chunks_used", 0),
        },
    )
