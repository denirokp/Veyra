"""Сборка Confluence-отчёта по результату veyra-mcp.check_initiative.

ЧЕРНОВИК (Фаза 1, Трек F). Формат — 3-колоночная таблица как у скилла
quality-metrics: Расхождение | Источник | Рекомендация. Только stdlib.
"""
from __future__ import annotations

import json
import sys


def build_report(result: dict) -> str:
    """result — ответ check_initiative. Возвращает Confluence-разметку."""
    if result.get("stub"):
        return (
            "h2. Veyra — отчёт\n\n"
            "{warning}veyra-mcp в skeleton-режиме (Фаза 1): реальных находок "
            "пока нет. Отчёт станет содержательным после Фазы 2.{warning}\n"
        )
    findings = result.get("findings", [])
    lines = [
        "h2. Veyra — расхождения с корпусом",
        "",
        "|| Расхождение || Источник || Рекомендация ||",
    ]
    for f in findings:
        lines.append(
            f"| {f.get('statement', '')} "
            f"| {f.get('source', '')} "
            f"| {f.get('recommendation', '')} |"
        )
    if not findings:
        lines.append("| Расхождений не найдено | — | — |")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    raw = sys.stdin.read()
    if not raw.strip():
        print("Передай JSON-ответ check_initiative через stdin")
        sys.exit(1)
    print(build_report(json.loads(raw)))
