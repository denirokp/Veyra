"""Singleton clients для Anthropic LLM и OpenAI Embeddings, плюс retry-обёртка."""
from __future__ import annotations

import asyncio
import logging
from typing import Awaitable, Callable, TypeVar

import anthropic
import openai

from app.settings import settings

logger = logging.getLogger(__name__)

_anthropic: anthropic.AsyncAnthropic | None = None
_openai: openai.AsyncOpenAI | None = None

T = TypeVar("T")


def get_llm() -> anthropic.AsyncAnthropic:
    global _anthropic
    if _anthropic is None:
        kwargs: dict = {"api_key": settings.ANTHROPIC_API_KEY}
        if settings.ANTHROPIC_BASE_URL:
            kwargs["base_url"] = settings.ANTHROPIC_BASE_URL
        _anthropic = anthropic.AsyncAnthropic(**kwargs)
    return _anthropic


def get_embeddings_client() -> openai.AsyncOpenAI:
    global _openai
    if _openai is None:
        kwargs: dict = {"api_key": settings.OPENAI_API_KEY}
        if settings.OPENAI_BASE_URL:
            kwargs["base_url"] = settings.OPENAI_BASE_URL
        _openai = openai.AsyncOpenAI(**kwargs)
    return _openai


async def _with_retry(
    fn: Callable[[], Awaitable[T]],
    *,
    max_attempts: int = 3,
    base_delay: float = 1.0,
    label: str = "llm",
) -> T:
    """Экспоненциальный backoff: 1s → 2s → 4s. Бросает последнюю ошибку, если все попытки упали."""
    last_exc: Exception | None = None
    for attempt in range(max_attempts):
        try:
            return await fn()
        except Exception as exc:  # ловим всё, включая APIConnectionError / RateLimitError
            last_exc = exc
            if attempt == max_attempts - 1:
                logger.error("%s retry exhausted (%d attempts): %s", label, max_attempts, exc)
                break
            delay = base_delay * (2 ** attempt)
            logger.warning("%s attempt %d/%d failed (%s), retry in %.1fs",
                           label, attempt + 1, max_attempts, exc, delay)
            await asyncio.sleep(delay)
    assert last_exc is not None
    raise last_exc


async def embed(texts: list[str]) -> list[list[float]]:
    """Возвращает эмбеддинги для списка текстов. С ретраями."""
    async def _call() -> list[list[float]]:
        client = get_embeddings_client()
        response = await client.embeddings.create(
            model=settings.EMBEDDING_MODEL,
            input=texts,
        )
        return [item.embedding for item in response.data]

    return await _with_retry(_call, label="embed")


async def embed_one(text: str) -> list[float]:
    results = await embed([text])
    return results[0]


async def call_llm(
    *,
    system: str,
    messages: list[dict],
    max_tokens: int,
) -> str:
    """Унифицированный LLM-вызов с ретраями. Возвращает текст первого блока ответа."""
    async def _call() -> str:
        llm = get_llm()
        response = await llm.messages.create(
            model=settings.LLM_MODEL,
            max_tokens=max_tokens,
            system=system,
            messages=messages,
        )
        return response.content[0].text.strip()

    return await _with_retry(_call, label="llm")
