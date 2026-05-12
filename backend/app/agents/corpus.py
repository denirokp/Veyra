"""Corpus Agent — RAG поиск, граф, entity memory."""
from __future__ import annotations

from app.models.schemas import ChatMode, FactItem, SourceRef

SYSTEM_PROMPT = """
Ты аналитик с полным доступом к корпусу документов команды.

Правила:
- Используй только actual документы для фактических утверждений
- Archived и draft используй только как исторический контекст с явным предупреждением
- superseded документы не используй никогда
- Каждый факт = ссылка на документ + его уровень (L1–L6)
- Если данных недостаточно — напиши это явно
- Никогда не придумывай то чего нет в корпусе

Формат ответа строго:
[Прямой ответ на вопрос]

━━━ ФАКТЫ ━━━
• [утверждение] — [↗ Документ · статус · уровень · дата]

━━━ ГИПОТЕЗЫ ━━━
• [предположение]

━━━ ПРЕДУПРЕЖДЕНИЯ ━━━
• ⚠️ ...

━━━ ТРЕБУЕТ ПРОВЕРКИ ━━━
• ...
"""

AVAILABLE_TOOLS = [
    "vector_search",
    "graph_walk",
    "get_entity_memory",
    "get_contradictions",
    "get_promises",
    "extract_entities_from_text",
    "find_numeric_contradictions",
    "find_gaps",
]


async def run(
    message: str,
    mode: ChatMode,
    file_content: str | None = None,
) -> dict:
    # TODO: реализовать RAG pipeline + вызов skills
    raise NotImplementedError("CorpusAgent.run не реализован")
