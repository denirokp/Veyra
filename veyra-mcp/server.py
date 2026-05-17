"""veyra-mcp — MCP-сервер Veyra.

СЛОЙ ДАННЫХ. veyra-mcp не рассуждает и не вызывает LLM в живом пути —
он только ПОДТЯГИВАЕТ материал из корпоративной памяти Veyra:
фрагменты документов, предвычисленные расхождения/обещания, карточки
документов. Рассуждение (синтез ответа, написание, веб-обогащение,
анализ серых зон) делает Claude — veyra-mcp даёт ему сырьё.

Три слоя архитектуры:
  1. Индексация (батч) — детекторы движка варят «бульон» в таблицы.
  2. veyra-mcp (живой путь) — ЧИСТЫЕ данные, ноль LLM, ноль токенов.
  3. Claude — берёт данные veyra-mcp и рассуждает поверх.

ЭТАП: alpha — не в production mcp-registry до полного retrieval-гейта.

Запуск:
    pip install -r requirements.txt
    VEYRA_BACKEND_URL=http://localhost:8000 python server.py
"""
from __future__ import annotations

import os

import httpx
from mcp.server.fastmcp import FastMCP

BACKEND_URL = os.getenv("VEYRA_BACKEND_URL", "http://localhost:8000").rstrip("/")
BACKEND_TOKEN = os.getenv("VEYRA_BACKEND_TOKEN", "")
HTTP_TIMEOUT = float(os.getenv("VEYRA_HTTP_TIMEOUT", "60"))

mcp = FastMCP(
    "veyra",
    host=os.getenv("VEYRA_MCP_HOST", "0.0.0.0"),
    port=int(os.getenv("VEYRA_MCP_PORT", "8765")),
)


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
async def search_corpus(query: str, top_k: int = 10) -> dict:
    """Поиск по корпоративной памяти — возвращает РЕЛЕВАНТНЫЕ ФРАГМЕНТЫ
    документов (сырьё, не готовый ответ). Синтезируй ответ сам из этих
    фрагментов и ссылайся на документы-источники. Используй, чтобы
    собрать материал по теме перед разбором, написанием или сверкой.
    """
    return {"passages": await _get("/api/retrieve", {"query": query, "top_k": top_k})}


@mcp.tool()
async def find_numeric_contradictions() -> dict:
    """Предвычисленные ЧИСЛОВЫЕ расхождения корпуса — одна метрика с
    разными значениями (между документами и внутри документа).
    Готовая таблица, без LLM-вызова.
    """
    return {"numeric_contradictions": await _get("/api/contradictions/numeric")}


@mcp.tool()
async def find_logic_contradictions() -> dict:
    """Предвычисленные ЛОГИЧЕСКИЕ расхождения корпуса — несовместимые по
    смыслу утверждения. Готовая таблица, без LLM-вызова.
    """
    return {"logic_contradictions": await _get("/api/contradictions/logic")}


@mcp.tool()
async def find_open_promises() -> dict:
    """Предвычисленные незакрытые обещания (open / overdue) — что
    обещали в документах и не отметили выполненным. Готовая таблица.
    """
    return {"promises": await _get("/api/promises")}


@mcp.tool()
async def list_documents() -> dict:
    """Список документов корпуса (id, название, статус, тип) — чтобы
    понять, что вообще есть в памяти, и выбрать документ для разбора.
    """
    return {"documents": await _get("/api/documents")}


@mcp.tool()
async def get_document(doc_id: str) -> dict:
    """Карточка документа по id: название, статус, иерархия, ссылка,
    число чанков, дата индексации.
    """
    return await _get(f"/api/documents/{doc_id}")


@mcp.tool()
async def corpus_stats() -> dict:
    """Сводка по корпусу: число документов, расхождений, обещаний,
    логических сигналов.
    """
    return await _get("/api/docs/stats")


@mcp.tool()
async def health() -> dict:
    """Доступность движка Veyra (backend)."""
    res = await _get("/health")
    if isinstance(res, dict) and res.get("error"):
        return {"status": "backend_unreachable", "backend": BACKEND_URL,
                "detail": res["error"]}
    return {"status": "ok", "backend": BACKEND_URL}


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
