"""Agent Metrics endpoint — будущая интеграция с Redash MCP.

Текущая реализация явно отвечает 501 Not Implemented, чтобы клиенты
не делали вид что у нас есть рабочие метрики. Когда подключим Redash —
заменим на реальный proxy.
"""
from fastapi import APIRouter, HTTPException

router = APIRouter(tags=["metrics"])


@router.get("/metrics/agent")
async def agent_metrics(query: str = ""):
    raise HTTPException(
        status_code=501,
        detail="Agent metrics не подключены. Настройте Redash MCP-сервер.",
    )


@router.get("/metrics/dashboards")
async def list_dashboards():
    raise HTTPException(
        status_code=501,
        detail="Redash dashboards не подключены.",
    )
