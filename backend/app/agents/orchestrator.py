"""Orchestrator — анализ запроса, роутинг к агентам, синтез финального ответа."""
from __future__ import annotations

from dataclasses import dataclass, field

from app.models.schemas import ChatMode, ChatRequest, ChatResponse


@dataclass
class RoutingPlan:
    agents: list[str]
    execution: str = "sequential"  # sequential | parallel
    detected_mode: ChatMode = ChatMode.search


TRIGGER_WORDS: dict[ChatMode, list[str]] = {
    ChatMode.contradictions: ["расхождения", "противоречия", "проверь цифры", "конфликт"],
    ChatMode.promises: ["обещали", "не сделали", "план", "выполнили"],
    ChatMode.gaps: ["не видим", "пропустили", "серые зоны", "чего нет"],
    ChatMode.write: ["напиши", "подготовь", "сделай документ", "составь"],
    ChatMode.validate: ["проверь инициативу", "стоит ли", "оцени", "что думаешь"],
    ChatMode.research: ["рынок", "конкуренты", "что делают другие"],
}


def _detect_mode(message: str) -> ChatMode:
    lower = message.lower()
    for mode, triggers in TRIGGER_WORDS.items():
        if any(t in lower for t in triggers):
            return mode
    return ChatMode.search


def build_routing_plan(request: ChatRequest) -> RoutingPlan:
    mode = request.mode or _detect_mode(request.message)
    agents = ["corpus"]
    if mode == ChatMode.research:
        agents.append("market")
    return RoutingPlan(
        agents=agents,
        execution="parallel" if len(agents) > 1 else "sequential",
        detected_mode=mode,
    )


async def run(request: ChatRequest) -> ChatResponse:
    plan = build_routing_plan(request)

    # TODO: вызов агентов по плану + синтез ответа через LLM
    raise NotImplementedError("Orchestrator.run не реализован")
