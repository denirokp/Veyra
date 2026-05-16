"""Orchestrator — приём запроса, делегирование corpus-агенту, синтез ответа.

Чат — единый разговорный режим: corpus-агент сам решает через tool-use loop,
что делать с запросом. Структурный разбор инициатив — отдельный поток
(эндпоинт /initiative-review), не через чат.
"""
from __future__ import annotations

import base64
import time

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents import corpus as corpus_agent
from app.models.schemas import ChatRequest, ChatResponse


def _decode_file(file_b64: str) -> str:
    try:
        return base64.b64decode(file_b64).decode("utf-8", errors="replace")
    except Exception:
        return ""


async def run(request: ChatRequest, db: AsyncSession) -> ChatResponse:
    t0 = time.monotonic()

    file_content = _decode_file(request.file) if request.file else None

    result = await corpus_agent.run(
        message=request.message,
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
            "agents_used": result.get("agents_used", ["corpus"]),
            "latency_ms": latency_ms,
            "chunks_retrieved": result.get("chunks_used", 0),
        },
    )
