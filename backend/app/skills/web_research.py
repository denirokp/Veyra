"""Web search для внешнего контекста.

Когда запрос требует «опыта из вне», best practices, бенчмарков — подтягиваем
несколько результатов из web-поиска и инжектим в LLM-промпт как внешний
контекст с disclaimer.

Поддерживает два провайдера:
- Tavily (платный, лучше качество для research): https://tavily.com
- Brave Search (free tier 2000 запросов/мес): https://brave.com/search/api

Автоматически отключается если ни один API-ключ не задан в .env.
"""
from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

import httpx

from app.settings import settings

logger = logging.getLogger(__name__)


# Триггеры в запросе на которые мы хотим веб-поиск
EXTERNAL_TRIGGERS = (
    "опыт из вне", "опыт изне", "извне", "внешн", "best practices",
    "бенчмарк", "benchmark", "как делают", "конкурент", "competitor",
    "индустри", "industry", "мировой опыт", "что в мире",
    "what does", "how do other", "market practice", "лучшие практики",
    "примеры из", "примеры с рынка", "примеры рынка", "опыт компаний",
    "из мира", "рыночный опыт", "опыт стартап", "опыт sass",
    "опыт saas", "в saas", "best in class",
)


def _generate_search_query(user_query: str) -> str:
    """Извлекает из пользовательского запроса ту часть, которую имеет смысл
    искать в интернете. Убирает «исходя из документа X», ссылки на внутренние
    инициативы — оставляет смысловое ядро."""
    q = user_query
    # Убираем «исходя из / описанн в / документ X»
    q = re.sub(r"\s*(?:исходя из|описанн[ыо]\w*\s+в|из документа|в нашем|внутреннем)[^.]*?документ\w*", "", q, flags=re.IGNORECASE)
    q = re.sub(r"\s*возьми\s*(?:также|еще)?\s*опыт[а-яё\s]*", "", q, flags=re.IGNORECASE)
    # Чистка пунктуации в конце
    q = re.sub(r"[?.!]+$", "", q).strip()
    # Ограничение длины запроса для search API (обычно 300-500 символов хорошо)
    return q[:300]


def should_do_web_search(query: str) -> bool:
    """Эвристика: есть ли в запросе явный сигнал что нужен внешний контекст."""
    if not (settings.TAVILY_API_KEY or settings.BRAVE_API_KEY):
        return False
    q = (query or "").lower()
    return any(t in q for t in EXTERNAL_TRIGGERS)


async def _tavily_search(query: str, max_results: int) -> list[dict]:
    """Tavily Search API. Возвращает list[{title, url, content}]."""
    if not settings.TAVILY_API_KEY:
        return []
    payload = {
        "api_key": settings.TAVILY_API_KEY,
        "query": query,
        "max_results": max_results,
        "search_depth": "advanced",  # лучше для research
        "include_answer": False,
    }
    async with httpx.AsyncClient(timeout=20.0) as client:
        try:
            r = await client.post("https://api.tavily.com/search", json=payload)
            r.raise_for_status()
            data = r.json()
        except Exception as exc:
            logger.warning("tavily search failed: %s", exc)
            return []
    items = []
    for it in (data.get("results") or [])[:max_results]:
        items.append({
            "title": it.get("title", ""),
            "url": it.get("url", ""),
            "content": (it.get("content") or "")[:1500],
        })
    return items


async def _brave_search(query: str, max_results: int) -> list[dict]:
    """Brave Search API. Возвращает list[{title, url, content}]."""
    if not settings.BRAVE_API_KEY:
        return []
    headers = {
        "X-Subscription-Token": settings.BRAVE_API_KEY,
        "Accept": "application/json",
    }
    params = {"q": query, "count": max_results, "result_filter": "web"}
    async with httpx.AsyncClient(timeout=20.0) as client:
        try:
            r = await client.get(
                "https://api.search.brave.com/res/v1/web/search",
                headers=headers, params=params,
            )
            r.raise_for_status()
            data = r.json()
        except Exception as exc:
            logger.warning("brave search failed: %s", exc)
            return []
    items = []
    for it in (data.get("web", {}).get("results") or [])[:max_results]:
        # Brave даёт description, не полный content — но это лучше чем ничего
        items.append({
            "title": it.get("title", ""),
            "url": it.get("url", ""),
            "content": (it.get("description") or "")[:800],
        })
    return items


async def search(query: str, max_results: int = 5) -> list[dict]:
    """Универсальный поиск — Tavily если есть ключ, иначе Brave."""
    if settings.TAVILY_API_KEY:
        return await _tavily_search(query, max_results)
    if settings.BRAVE_API_KEY:
        return await _brave_search(query, max_results)
    return []


def format_for_prompt(results: list[dict], max_chars: int = 8000) -> str:
    """Формирует блок «ВНЕШНИЙ КОНТЕКСТ» для подмешивания в промпт."""
    if not results:
        return ""
    parts = ["ВНЕШНИЙ КОНТЕКСТ ИЗ ИНТЕРНЕТА (используй как hypothesis с disclaimer):\n"]
    total = 0
    for i, r in enumerate(results, 1):
        block = (
            f"[Web-источник {i}: {r['title']}]\n"
            f"URL: {r['url']}\n"
            f"{r['content']}\n"
        )
        if total + len(block) > max_chars:
            break
        parts.append(block)
        total += len(block)
    return "\n".join(parts)


_INTL_TOPICS = (
    "amazon", "shopify", "etsy", "stripe", "ebay", "alibaba",
    "saas", "best practices", "industry", "global",
    "pendo", "appcues", "userpilot", "intercom", "segment",
    "mixpanel", "amplitude",
)


def _maybe_english_query(query: str) -> str | None:
    """Если запрос про международные продукты на русском — генерируем
    его английскую версию для лучших результатов поиска. Иначе None."""
    q_lower = query.lower()
    if not any(t in q_lower for t in _INTL_TOPICS):
        return None
    # Простая замена ключевых терминов
    replacements = {
        "онбординг": "onboarding",
        "продавцов": "sellers",
        "продавцы": "sellers",
        "продавца": "seller",
        "продавец": "seller",
        "обучени\\w*": "training",
        "лучшие практики": "best practices",
        "опыт": "experience",
        "конкурент\\w*": "competitors",
        "из мира": "in",
        "в мире": "global",
        "как организован\\w*": "how is organized",
        "как делают": "how do",
        "стратеги\\w*": "strategy",
        "маркетплейс\\w*": "marketplace",
        "бенчмарк\\w*": "benchmark",
        "индустри\\w*": "industry",
        "примеры": "examples",
        " в ": " in ",
        " на ": " on ",
        " из ": " from ",
        " по ": " on ",
        " для ": " for ",
        " с ": " with ",
        " и ": " and ",
    }
    en = query
    for ru, en_term in replacements.items():
        en = re.sub(ru, en_term, en, flags=re.IGNORECASE)
    # Финал: если в строке ещё много кириллицы — возможно перевод не помог.
    # Считаем кириллические символы — если их >30% — сдаёмся.
    cyrillic = sum(1 for c in en if "Ѐ" <= c <= "ӿ")
    if cyrillic / max(1, len(en)) > 0.3:
        return None
    return en[:300]


async def do_research(query: str, max_results: int = 10) -> str:
    """Полный пайплайн: query → результаты поиска → форматированный блок.
    Для международных тем делает 2 поиска: на русском и на английском —
    больше шансов поймать качественные источники.
    Возвращает пустую строку если поиск выключен или ничего не нашлось."""
    search_q = _generate_search_query(query)
    if not search_q:
        return ""

    all_results: list[dict] = []
    seen_urls: set[str] = set()

    # Основной поиск
    results = await search(search_q, max_results=max_results)
    for r in results:
        if r.get("url") and r["url"] not in seen_urls:
            seen_urls.add(r["url"])
            all_results.append(r)

    # Дополнительный поиск на английском для международных тем.
    # Brave free tier лимит 1 req/sec → ждём 1.1 сек перед вторым вызовом.
    en_q = _maybe_english_query(search_q)
    if en_q and en_q != search_q:
        await asyncio.sleep(1.1)
        en_results = await search(en_q, max_results=max_results)
        for r in en_results:
            if r.get("url") and r["url"] not in seen_urls:
                seen_urls.add(r["url"])
                all_results.append(r)
        logger.info("web_research: +en query %r → %d more results", en_q[:50], len(en_results))

    if not all_results:
        return ""
    logger.info("web_research: %d total results for %r", len(all_results), search_q[:60])
    return format_for_prompt(all_results, max_chars=12000)
