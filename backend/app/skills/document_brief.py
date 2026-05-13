"""Skill: document_brief — структурированный обзор всего документа.

Один LLM-вызов на полный текст, чтобы получить компактное представление
документа для document-level анализа (full mode и т.п.). Без этого LLM видит
только фрагменты через RAG и теряет общую картину.
"""
from __future__ import annotations

import logging

from app.clients import call_llm

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = """\
Ты аналитик корпоративной памяти. На входе — полный текст одного документа \
команды (стратегия, ресёрч, план, ретро). На выходе — структурированный обзор \
для базы знаний.

ФОРМАТ (строго markdown, без лишних слов):

## Назначение
1-3 предложения: о чём документ, зачем он, для кого.

## Ключевые цифры
Маркеры: метрика — значение с единицей — период — источник в документе \
(раздел/таблица/appendix).

## Инициативы / стримы
Маркеры: название инициативы — ожидаемый эффект — владелец/команда — сроки \
(если указаны).

## Решения и обязательства
Что зафиксировано как принятое или запланированное (с датами/owner'ами).

## Риски и расхождения
Маркеры: риск — вероятность/импакт (если указано) — митигация.

## Открытые вопросы / next steps
Что ещё не решено или требует следующих шагов.

ПРАВИЛА:
1. Только то что явно в тексте. НЕ ВЫДУМЫВАЙ.
2. Числа давай с единицами и периодом (например: "4.2 Bn RUB cumulative \
revenue by CY2030").
3. Если секция пуста — пиши "Нет данных" (не выдумывай).
4. Имена/команды копируй точно как в документе.
5. Не превышай 2500 слов. Будь плотным.\
"""

# Лимит на размер документа — Moonshot 128K context позволяет ~100K input, но
# мы оставляем запас на system prompt + ответ. 40K символов ≈ 10K токенов.
MAX_INPUT_CHARS = 40_000


async def generate_document_brief(text: str, title: str) -> str:
    """Возвращает markdown-бриф документа. На пустом тексте — пустая строка."""
    if not text or not text.strip():
        return ""
    truncated = text[:MAX_INPUT_CHARS]
    if len(text) > MAX_INPUT_CHARS:
        truncated += f"\n\n[...документ урезан до {MAX_INPUT_CHARS} символов]"

    user_message = f"Документ: «{title}»\n\n{truncated}"
    try:
        return await call_llm(
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
            max_tokens=3000,
        )
    except Exception as exc:
        logger.error("brief generation failed: %s", exc)
        return ""
