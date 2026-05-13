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
    "опыт из вне", "внешний опыт", "best practices", "бенчмарк",
    "как делают", "конкурент", "индустри", "мировой опыт",
    "what does", "how do other", "market practice",
)


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


async def do_research(query: str, max_results: int = 5) -> str:
    """Полный пайплайн: query → результаты поиска → форматированный блок.
    Возвращает пустую строку если поиск выключен или ничего не нашлось."""
    results = await search(query, max_results=max_results)
    if not results:
        return ""
    logger.info("web_research: %d results for %r", len(results), query[:60])
    return format_for_prompt(results)
