"""Visible plan announcer — короткая «постановка задачи» перед ответом.

Перед основным синтезом просим LLM одной короткой строкой описать
что он собирается сделать: что прочитал, что синтезирует, какой опыт
подтянет. Эта строка prepend'ится к answer как блок blockquote,
давая пользователю ощущение «агент думает», как в Perplexity Deep
Research или GPT Researcher.

Это НЕ полноценный ReAct (нет реальных tool calls), но даёт прозрачность
и снижает waiting anxiety при 30-60 секундной латенси.
"""
from __future__ import annotations

import logging
import re

from app.clients import call_llm

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = """\
Ты — аналитик. Получил запрос пользователя и список документов в работе.
Напиши ОДИН короткий абзац (2-3 предложения) — план как ты собираешься \
ответить.

Стиль — деловой, без «Я» в начале каждой фразы. Глагол прошедшего времени \
или причастие («Прочитал X», «Синтезирую Y», «Подтяну внешний опыт по Z»).

Что упомянуть:
1. Какие документы из списка ты считаешь основными для запроса
2. Что планируешь синтезировать
3. Если запрос требует внешнего опыта — какие индустрии/продукты подтянешь \
из pretrain знаний (Amazon, Ozon, Pendo, SaaS-фреймворки и т.д.)

Без markdown-заголовков. Просто текст одним блоком. Без префиксов вроде \
«План:» или «Подход:».\
"""


async def announce_plan(query: str, doc_titles: list[str]) -> str:
    """Возвращает короткий blockquote-плейн для prepend к answer.
    На ошибках возвращает пустую строку (gracefully)."""
    if not doc_titles:
        return ""
    titles_block = "\n".join(f"- {t}" for t in doc_titles[:20])
    user_msg = (
        f"ЗАПРОС:\n{query}\n\n"
        f"ДОКУМЕНТЫ В РАБОТЕ:\n{titles_block}"
    )
    try:
        raw = await call_llm(
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_msg}],
            max_tokens=200,
        )
    except Exception as exc:
        logger.warning("plan_announcer failed (skipping): %s", exc)
        return ""

    text = (raw or "").strip()
    # Защита от случайных артефактов
    if not text or len(text) > 600:
        return ""
    # Чистим возможные markdown-обёртки
    text = re.sub(r"^[#>*\-]+\s*", "", text).strip()
    return text
