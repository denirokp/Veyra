"""Обёртка скилла veyra для вызова veyra-mcp.check_initiative.

ЧЕРНОВИК (Фаза 1, Трек F). veyra-mcp сейчас возвращает заглушку — скрипт
уже работает end-to-end по транспорту, реальные находки появятся после
заливки логики в Фазе 2 (Трек E). Только stdlib — никаких зависимостей.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request

VEYRA_MCP_URL = os.getenv("VEYRA_MCP_URL", "http://localhost:8000")
DEV_TOKEN = os.getenv("VEYRA_MCP_DEV_TOKEN", "")


def check_initiative(text: str) -> dict:
    headers = {"Content-Type": "application/json"}
    if DEV_TOKEN:
        headers["Authorization"] = f"Bearer {DEV_TOKEN}"
    req = urllib.request.Request(
        f"{VEYRA_MCP_URL}/tools/check_initiative",
        data=json.dumps({"text": text}).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


if __name__ == "__main__":
    initiative = " ".join(sys.argv[1:]) if sys.argv[1:] else sys.stdin.read()
    if not initiative.strip():
        print("Передай текст инициативы аргументом или через stdin")
        sys.exit(1)
    print(json.dumps(check_initiative(initiative), ensure_ascii=False, indent=2))
