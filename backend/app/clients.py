"""LLM-клиент (OpenAI-совместимый, поддерживает Kimi/Moonshot, OpenAI, Avito proxy)
и локальные embeddings через sentence-transformers."""
from __future__ import annotations

import asyncio
import json
import logging
import random
import re
from typing import Awaitable, Callable, TypeVar

import openai

from app.settings import settings

logger = logging.getLogger(__name__)

_llm_client: openai.AsyncOpenAI | None = None
_embedder = None  # SentenceTransformer, lazy-loaded

# Глобальный лимит одновременных LLM-вызовов. Moonshot не штатно отдаёт 429,
# но без лимита find_logic_signals может пустить 5-10 параллельных запросов
# за секунду и упереться в rate-limit или таймауты.
_LLM_SEMAPHORE = asyncio.Semaphore(3)

T = TypeVar("T")


def get_llm_client() -> openai.AsyncOpenAI:
    """OpenAI-совместимый клиент. Для Kimi подставляем base_url=https://api.moonshot.ai/v1."""
    global _llm_client
    if _llm_client is None:
        _llm_client = openai.AsyncOpenAI(
            api_key=settings.LLM_API_KEY,
            base_url=settings.LLM_BASE_URL or None,
            timeout=120.0,
        )
    return _llm_client


def get_embedder():
    """Лениво инициализирует sentence-transformers модель. Первый вызов тяжёлый (~5s + загрузка)."""
    global _embedder
    if _embedder is None:
        from sentence_transformers import SentenceTransformer
        logger.info("Загружаю embedding-модель: %s", settings.EMBEDDING_MODEL)
        _embedder = SentenceTransformer(
            settings.EMBEDDING_MODEL,
            device="cpu",
            model_kwargs={"low_cpu_mem_usage": False},
        )
        logger.info("Embedding-модель загружена, dim=%d", _embedder.get_sentence_embedding_dimension())
    return _embedder


async def _with_retry(
    fn: Callable[[], Awaitable[T]],
    *,
    max_attempts: int = 3,
    base_delay: float = 1.0,
    label: str = "llm",
) -> T:
    """Экспоненциальный backoff с jitter: 1±0.5 → 2±1 → 4±2 сек.
    Jitter нужен чтобы N параллельных запросов не ретраились синхронно после
    общего сетевого глитча и не штормили API в один момент."""
    last_exc: Exception | None = None
    for attempt in range(max_attempts):
        try:
            return await fn()
        except Exception as exc:
            last_exc = exc
            if attempt == max_attempts - 1:
                logger.error("%s retry exhausted (%d attempts): %s", label, max_attempts, exc)
                break
            base = base_delay * (2 ** attempt)
            delay = base + random.uniform(0, base * 0.5)
            logger.warning("%s attempt %d/%d failed (%s), retry in %.1fs",
                           label, attempt + 1, max_attempts, exc, delay)
            await asyncio.sleep(delay)
    assert last_exc is not None
    raise last_exc


async def embed(texts: list[str]) -> list[list[float]]:
    """Локальный embeddings batch. Гоняем encode в отдельном thread'е чтобы не блокировать loop."""
    if not texts:
        return []

    def _encode() -> list[list[float]]:
        model = get_embedder()
        vectors = model.encode(
            texts,
            batch_size=32,
            show_progress_bar=False,
            convert_to_numpy=True,
            normalize_embeddings=True,
        )
        return [v.tolist() for v in vectors]

    return await asyncio.to_thread(_encode)


async def embed_one(text: str) -> list[float]:
    results = await embed([text])
    return results[0]


def fast_model() -> str:
    """Модель для механических skills. LLM_MODEL_FAST если задан, иначе LLM_MODEL."""
    return settings.LLM_MODEL_FAST or settings.LLM_MODEL


async def call_llm(
    *,
    system: str,
    messages: list[dict],
    max_tokens: int,
    model: str | None = None,
) -> str:
    """LLM-вызов через OpenAI-совместимый API. С ретраями и rate-limit.
    model=None → settings.LLM_MODEL. Возвращает текст ответа."""
    async def _call() -> str:
        async with _LLM_SEMAPHORE:
            client = get_llm_client()
            response = await client.chat.completions.create(
                model=model or settings.LLM_MODEL,
                max_tokens=max_tokens,
                messages=[{"role": "system", "content": system}, *messages],
            )
        # reasoning-модели и редкие провайдер-ошибки иногда возвращают content=None
        return (response.choices[0].message.content or "").strip()

    return await _with_retry(_call, label="llm")


def parse_json_array(raw: str) -> list[dict]:
    """Толерантный парсер JSON-массива объектов из LLM-ответа.

    Терпит три типичные болезни LLM-вывода:
    1. markdown-обёртку ```json ... ``` (модель игнорирует "без markdown");
    2. поясняющий текст до/после массива;
    3. обрыв ответа по лимиту токенов — тогда закрывающей ] нет, и мы
       собираем все целые объекты по отдельности (объекты skill-ответов
       плоские, без вложенных {}), теряя только последний неполный.
    """
    if not raw:
        return []
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"\n?```\s*$", "", text).strip()

    try:
        data = json.loads(text)
        if isinstance(data, list):
            return [x for x in data if isinstance(x, dict)]
    except json.JSONDecodeError:
        pass

    match = re.search(r"\[.*\]", text, re.DOTALL)
    if match:
        try:
            data = json.loads(match.group())
            if isinstance(data, list):
                return [x for x in data if isinstance(x, dict)]
        except json.JSONDecodeError:
            pass

    # Спасение оборванного ответа — объект за объектом.
    out: list[dict] = []
    for obj in re.findall(r"\{[^{}]*\}", text, re.DOTALL):
        try:
            parsed = json.loads(obj)
            if isinstance(parsed, dict):
                out.append(parsed)
        except json.JSONDecodeError:
            continue
    return out


# ── Backward-compat ──────────────────────────────────────────────────────────
# Старые места кода могут вызывать get_llm() — оставляем алиас, но рекомендуем call_llm().
def get_llm() -> openai.AsyncOpenAI:
    return get_llm_client()
