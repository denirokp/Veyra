"""Авторизация veyra-mcp.

ВНИМАНИЕ: на этапе skeleton это ЗАГЛУШКА. Реальная интеграция с Keycloak
Avito (как у остальных MCP в hub) требует параметров realm/issuer/audience
из инфры и делается при подключении к PaaS. Доступ сейчас — только
разработчикам, сервис не регистрируется в production mcp-registry.

TODO (Фаза 1, Трек B, шаг 3): подключить Keycloak — проверка Bearer-JWT
против realm Avito. Здесь меняется только тело require_auth, сигнатура
остаётся, эндпоинты в main.py не трогаются.
"""
from __future__ import annotations

import os

from fastapi import Header, HTTPException, status

# Временный dev-режим. Если VEYRA_MCP_DEV_TOKEN задан — пускаем только с ним.
# Если не задан — сервис открыт (локальная разработка). В PaaS это
# заменяется проверкой Keycloak.
_DEV_TOKEN = os.getenv("VEYRA_MCP_DEV_TOKEN", "")


async def require_auth(authorization: str | None = Header(default=None)) -> None:
    """Заглушка авторизации. Реальный Keycloak — TODO Трека B."""
    if not _DEV_TOKEN:
        return  # локальная разработка без auth
    if authorization != f"Bearer {_DEV_TOKEN}":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Неверный или отсутствующий токен (skeleton dev-режим)",
        )
