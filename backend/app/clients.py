"""Singleton clients для Anthropic LLM и OpenAI Embeddings."""
from __future__ import annotations

import anthropic
import openai

from app.settings import settings

_anthropic: anthropic.AsyncAnthropic | None = None
_openai: openai.AsyncOpenAI | None = None


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


async def embed(texts: list[str]) -> list[list[float]]:
    """Возвращает эмбеддинги для списка текстов."""
    client = get_embeddings_client()
    response = await client.embeddings.create(
        model=settings.EMBEDDING_MODEL,
        input=texts,
    )
    return [item.embedding for item in response.data]


async def embed_one(text: str) -> list[float]:
    results = await embed([text])
    return results[0]
