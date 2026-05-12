"""Orchestrator — анализ запроса, роутинг к агентам, синтез финального ответа."""
from __future__ import annotations

import base64
import time

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents import corpus as corpus_agent
from app.models.schemas import ChatMode, ChatRequest, ChatResponse, FactItem

TRIGGER_WORDS: dict[ChatMode, list[str]] = {
    ChatMode.contradictions: ["расхождения", "противоречия", "проверь цифры", "конфликт данных"],
    ChatMode.promises: ["обещали", "не сделали", "что планировали", "реестр планов"],
    ChatMode.gaps: ["не видим", "пропустили", "серые зоны", "чего не хватает"],
    ChatMode.write: ["напиши", "подготовь", "сделай документ", "составь записку"],
    ChatMode.validate: ["проверь инициативу", "стоит ли", "оцени идею", "что думаешь"],
    ChatMode.research: ["рынок", "конкуренты", "что делают другие", "внешний рынок"],
}


def detect_mode(message: str) -> ChatMode:
    lower = message.lower()
    for mode, triggers in TRIGGER_WORDS.items():
        if any(t in lower for t in triggers):
            return mode
    return ChatMode.search


def _decode_file(file_b64: str) -> str:
    try:
        return base64.b64decode(file_b64).decode("utf-8", errors="replace")
    except Exception:
        return ""


async def run(request: ChatRequest, db: AsyncSession) -> ChatResponse:
    t0 = time.monotonic()

    mode = request.mode or detect_mode(request.message)
    file_content = _decode_file(request.file) if request.file else None

    # Вызов Corpus Agent
    result = await corpus_agent.run(
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
            "agents_used": result.get("agents_used", ["corpus"]),
            "latency_ms": latency_ms,
            "chunks_retrieved": result.get("chunks_used", 0),
        },
    )
