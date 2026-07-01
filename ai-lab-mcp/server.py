"""ai-lab-mcp — MCP-сервер AI Lab.

СЛОЙ ДАННЫХ. ai-lab-mcp не рассуждает и не вызывает LLM в живом пути —
он только ПОДТЯГИВАЕТ материал из корпоративной памяти AI Lab:
фрагменты документов, предвычисленные расхождения/обещания, карточки
документов. Рассуждение (синтез ответа, написание, веб-обогащение,
анализ серых зон) делает Claude — ai-lab-mcp даёт ему сырьё.

Три слоя архитектуры:
  1. Индексация (батч) — детекторы движка варят «бульон» в таблицы.
  2. ai-lab-mcp (живой путь) — ЧИСТЫЕ данные, ноль LLM, ноль токенов.
  3. Claude — берёт данные ai-lab-mcp и рассуждает поверх.

ЭТАП: alpha — не в production mcp-registry до полного retrieval-гейта.

Запуск:
    pip install -r requirements.txt
    AILAB_BACKEND_URL=http://localhost:8000 python server.py
"""
from __future__ import annotations

import functools
import hmac
import logging
import os
import time
from collections import defaultdict

import httpx
from mcp.server.fastmcp import FastMCP

logger = logging.getLogger("ai-lab-mcp")

BACKEND_URL = os.getenv("AILAB_BACKEND_URL", "http://localhost:8000").rstrip("/")
BACKEND_TOKEN = os.getenv("AILAB_BACKEND_TOKEN", "")
HTTP_TIMEOUT = float(os.getenv("AILAB_HTTP_TIMEOUT", "60"))
# Bearer-токен для ВХОДЯЩИХ запросов от Claude/Avito AI. Пустая строка =
# auth выключен (dev). В проде задавать через env / fly secrets.
MCP_AUTH_TOKEN = os.getenv("MCP_AUTH_TOKEN", "")

HOST = os.getenv("AILAB_MCP_HOST", "0.0.0.0")
PORT = int(os.getenv("AILAB_MCP_PORT", "8765"))

mcp = FastMCP("ai-lab", host=HOST, port=PORT)


# G6 — наблюдаемость: счётчик вызовов на каждый MCP-инструмент. Живой путь
# ai-lab-mcp не вызывает LLM (ноль токенов/стоимости), поэтому здесь считаем
# не $, а ЧИСЛО tool-call: что и как часто дёргает Claude. Счётчик in-process,
# сбрасывается при рестарте; видно в логах и через инструмент health().
_TOOL_CALLS: dict[str, int] = defaultdict(int)


def _tracked(fn):
    """Логирует и считает каждый вызов инструмента (имя, № вызова, латентность).
    Ставится ПОД @mcp.tool() — functools.wraps сохраняет сигнатуру и docstring,
    поэтому схема инструмента у FastMCP не меняется."""
    @functools.wraps(fn)
    async def wrapper(*args, **kwargs):
        _TOOL_CALLS[fn.__name__] += 1
        t0 = time.perf_counter()
        try:
            return await fn(*args, **kwargs)
        finally:
            logger.info(
                "tool=%s call#%d %.0fms",
                fn.__name__, _TOOL_CALLS[fn.__name__], (time.perf_counter() - t0) * 1000,
            )
    return wrapper


class BearerAuthASGI:
    """Чистый ASGI-middleware: проверяет `Authorization: Bearer <MCP_AUTH_TOKEN>`
    на каждом HTTP-запросе. В отличие от starlette BaseHTTPMiddleware НЕ
    оборачивает response — поэтому не вмешивается в SSE-стрим streamable-HTTP
    транспорта MCP (BaseHTTPMiddleware на стримах даёт тонкие баги). Сравнение
    constant-time (hmac.compare_digest) — публичный эндпоинт, защита от
    timing-перебора токена."""

    def __init__(self, app, token: str):
        self.app = app
        self._expected = f"Bearer {token}".encode()

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        auth = b""
        for name, value in scope.get("headers") or ():
            if name == b"authorization":
                auth = value
                break
        if not hmac.compare_digest(auth, self._expected):
            await send({
                "type": "http.response.start",
                "status": 401,
                "headers": [(b"content-type", b"application/json")],
            })
            await send({"type": "http.response.body", "body": b'{"error":"unauthorized"}'})
            return
        await self.app(scope, receive, send)


def _headers() -> dict:
    h = {"Content-Type": "application/json"}
    if BACKEND_TOKEN:
        h["Authorization"] = f"Bearer {BACKEND_TOKEN}"
    return h


async def _get(path: str, params: dict | None = None):
    """GET к движку. При недоступности возвращает {"error": ...}, не падает."""
    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
            r = await client.get(f"{BACKEND_URL}{path}", params=params, headers=_headers())
            r.raise_for_status()
            return r.json()
    except Exception as exc:  # noqa: BLE001
        return {"error": f"backend GET {path} failed: {exc}"}


@mcp.tool()
@_tracked
async def search_corpus(query: str, top_k: int = 10, workspace: str = "default") -> dict:
    """Поиск по корпоративной памяти — возвращает РЕЛЕВАНТНЫЕ ФРАГМЕНТЫ
    документов (сырьё, не готовый ответ). Синтезируй ответ сам из этих
    фрагментов и ссылайся на документы-источники. Используй, чтобы
    собрать материал по теме перед разбором, написанием или сверкой.

    workspace — корпус (команда/человек). Изолирован: поиск идёт только в
    указанном корпусе. По умолчанию `default`.
    """
    return {"passages": await _get(
        "/api/retrieve", {"query": query, "top_k": top_k, "workspace": workspace})}


@mcp.tool()
@_tracked
async def find_numeric_contradictions() -> dict:
    """Предвычисленные ЧИСЛОВЫЕ расхождения корпуса — одна метрика с
    разными значениями (между документами и внутри документа).
    Готовая таблица, без LLM-вызова. Каждая запись несёт severity:
    critical | medium | low — критичность по величине отрыва значений.
    """
    return {"numeric_contradictions": await _get("/api/contradictions/numeric")}


@mcp.tool()
@_tracked
async def find_logic_contradictions() -> dict:
    """Предвычисленные ЛОГИЧЕСКИЕ расхождения корпуса — несовместимые по
    смыслу утверждения. Готовая таблица, без LLM-вызова. Каждая запись
    несёт severity: critical | medium | low | unknown.
    """
    return {"logic_contradictions": await _get("/api/contradictions/logic")}


@mcp.tool()
@_tracked
async def find_open_promises() -> dict:
    """Предвычисленные незакрытые обещания (open / overdue) — что
    обещали в документах и не отметили выполненным. Готовая таблица.
    """
    return {"promises": await _get("/api/promises")}


@mcp.tool()
@_tracked
async def list_documents() -> dict:
    """Список документов корпуса (id, название, статус, тип) — чтобы
    понять, что вообще есть в памяти, и выбрать документ для разбора.
    """
    return {"documents": await _get("/api/documents")}


@mcp.tool()
@_tracked
async def get_document(doc_id: str) -> dict:
    """Полный текст документа корпуса по id — чтобы вчитаться в один
    документ целиком (агентный разбор, проверка цитаты). id берётся из
    search_corpus или list_documents.
    """
    return await _get(f"/api/documents/{doc_id}/text")


@mcp.tool()
@_tracked
async def corpus_stats() -> dict:
    """Сводка по корпусу: число документов, расхождений, обещаний,
    логических сигналов, а также last_indexed_at — когда корпус последний раз
    индексировался. Предвычисленные таблицы find_* отражают состояние на
    last_indexed_at, а не «сейчас»; используй это в контракте охвата.
    """
    return await _get("/api/docs/stats")


@mcp.tool()
@_tracked
async def health() -> dict:
    """Доступность движка AI Lab (backend) + счётчик вызовов инструментов
    (G6 — сколько раз с момента старта дёрнут каждый инструмент)."""
    res = await _get("/health")
    tool_calls = dict(_TOOL_CALLS)
    if isinstance(res, dict) and res.get("error"):
        return {"status": "backend_unreachable", "backend": BACKEND_URL,
                "detail": res["error"], "tool_calls": tool_calls}
    return {"status": "ok", "backend": BACKEND_URL, "tool_calls": tool_calls}


if __name__ == "__main__":
    if MCP_AUTH_TOKEN:
        import uvicorn
        # Оборачиваем ASGI-приложение MCP чистым ASGI-middleware (не
        # BaseHTTPMiddleware) — auth поверх streamable-HTTP без риска для стрима.
        app = BearerAuthASGI(mcp.streamable_http_app(), MCP_AUTH_TOKEN)
        uvicorn.run(app, host=HOST, port=PORT)
    else:
        # Dev-режим без auth — для локальной разработки.
        mcp.run(transport="streamable-http")
