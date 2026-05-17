"""veyra-mcp — MCP-сервер Veyra.

Тонкий MCP-фасад над движком Veyra. Инструменты проксируют запросы в
HTTP-API бэкенда (backend/): сам backend остаётся «толстым» сервисом
(retrieval + детекторы + память корпуса), а veyra-mcp отдаёт его наружу
как набор MCP-инструментов — чтобы Claude / Avito AI могли дёргать
корпоративную память Veyra из любого диалога.

ЭТАП: alpha. Регистрировать в production mcp-registry — только после
полного прохождения retrieval-гейта (ТЗ Принцип 1). Инструменты,
читающие предвычисленные таблицы (find_contradictions / find_gaps /
find_open_promises), безопасны; check_initiative и search_corpus
запускают LLM-логику движка.

Запуск:
    pip install -r requirements.txt
    VEYRA_BACKEND_URL=http://localhost:8000 python server.py

Транспорт — streamable-http (для remote-MCP в Avito mcp-hub).
"""
from __future__ import annotations

import os

import httpx
from mcp.server.fastmcp import FastMCP

BACKEND_URL = os.getenv("VEYRA_BACKEND_URL", "http://localhost:8000").rstrip("/")
BACKEND_TOKEN = os.getenv("VEYRA_BACKEND_TOKEN", "")
HTTP_TIMEOUT = float(os.getenv("VEYRA_HTTP_TIMEOUT", "240"))

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
    """GET к бэкенду. При недоступности возвращает {"error": ...}, не падает."""
    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
            r = await client.get(f"{BACKEND_URL}{path}", params=params, headers=_headers())
            r.raise_for_status()
            return r.json()
    except Exception as exc:  # noqa: BLE001
        return {"error": f"backend GET {path} failed: {exc}"}


async def _post(path: str, payload: dict):
    """POST к бэкенду. При недоступности возвращает {"error": ...}, не падает."""
    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
            r = await client.post(f"{BACKEND_URL}{path}", json=payload, headers=_headers())
            r.raise_for_status()
            return r.json()
    except Exception as exc:  # noqa: BLE001
        return {"error": f"backend POST {path} failed: {exc}"}


@mcp.tool()
async def search_corpus(query: str, top_k: int = 5) -> dict:
    """Поиск по корпоративной памяти Veyra — «что мы уже знаем про X».

    Возвращает синтезированный ответ с фактами и ссылками на
    документы-источники. Используй, когда нужно понять, что компания
    уже писала по теме, перед тем как писать новое.
    """
    return await _post("/api/chat", {"message": query, "mode": "search"})


@mcp.tool()
async def check_initiative(text: str) -> dict:
    """Сверка новой инициативы со стратегическим корпусом.

    Находит расхождения, противоречия с прошлыми решениями и пробелы.
    Используй при запросах «проверь инициативу», «согласуется ли это
    со стратегией», «нет ли противоречий с тем, что мы уже решили».
    """
    return await _post("/api/chat", {"message": text, "mode": "validate"})


@mcp.tool()
async def find_numeric_contradictions() -> dict:
    """Известные ЧИСЛОВЫЕ расхождения корпуса — одна метрика с разными
    значениями (между документами и внутри одного документа).
    Предвычислены при индексации.
    """
    return {"numeric_contradictions": await _get("/api/contradictions/numeric")}


@mcp.tool()
async def find_logic_contradictions() -> dict:
    """Известные ЛОГИЧЕСКИЕ расхождения корпуса — несовместимые по
    смыслу утверждения («здесь говорим одно, здесь другое»).
    Предвычислены при индексации.
    """
    return {"logic_contradictions": await _get("/api/contradictions/logic")}


@mcp.tool()
async def find_open_promises() -> dict:
    """Незакрытые обещания корпуса (open / overdue).

    Что было обещано в документах и не отмечено выполненным. Используй
    для «что мы обещали и не сделали».
    """
    return {"promises": await _get("/api/promises")}


@mcp.tool()
async def find_gaps() -> dict:
    """Серые зоны корпуса — темы и инициативы без ресурсов, владельцев
    или выпавшие между приоритетами. Используй для «что мы упустили».
    """
    return {"gaps": await _get("/api/docs/gaps")}


@mcp.tool()
async def write_draft(topic: str) -> dict:
    """Помощь в написании документа/инициативы по теме: собирает
    grounded-факты из корпуса и даёт черновик в стиле команды.
    Финальный текст пишет человек — это заготовка с опорой на реальные
    документы, а не готовый документ.
    """
    return await _post("/api/chat", {"message": topic, "mode": "write"})


@mcp.tool()
async def market_research(topic: str) -> dict:
    """Рыночный контекст по теме — практики конкурентов, бенчмарки,
    сопоставление с внешним рынком. Если у движка настроен веб-поиск
    (Tavily/Brave) — тянет свежие данные из интернета; без ключа
    отдаёт знания модели с явной пометкой.
    """
    return await _post("/api/chat", {"message": topic, "mode": "research"})


@mcp.tool()
async def get_document(doc_id: str) -> dict:
    """Карточка документа корпуса по id: название, статус, иерархия,
    ссылка, число чанков, дата индексации. Полный текст документа через
    API не отдаётся — цитаты бери из ответов search_corpus /
    check_initiative.
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
