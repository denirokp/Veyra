"""Agent Metrics endpoint — интеграция с Redash MCP (stub до подключения MCP-сервера)."""
from fastapi import APIRouter, HTTPException

router = APIRouter(tags=["metrics"])


@router.get("/metrics/agent")
async def agent_metrics(query: str = ""):
    """
    Заглушка для Agent Metrics / Redash MCP.
    После подключения Redash MCP-сервера этот endpoint будет проксировать запросы.
    """
    return {
        "status": "stub",
        "message": "Redash MCP интеграция не подключена. Настрой MCP-сервер для Redash.",
        "query": query,
        "data": [],
    }


@router.get("/metrics/dashboards")
async def list_dashboards():
    """Stub — список дашбордов из Redash."""
    return {
        "status": "stub",
        "dashboards": [],
        "message": "Redash MCP не подключён",
    }
