"""Сборка Confluence-страницы по результату инструмента veyra
(check_initiative / search_corpus).

Формат — заголовок + ответ + таблица расхождений + источники, по
образцу скилла quality-metrics. Только stdlib.

Вход (stdin): JSON-ответ инструмента veyra — структура движка:
{answer, facts[], warnings[], hypotheses[], requires_verification[], metadata}.
"""
from __future__ import annotations

import json
import sys


def build_report(result: dict) -> str:
    if result.get("error"):
        return (
            "h2. Veyra — отчёт\n\n"
            f"{{warning}}Veyra недоступна: {result['error']}{{warning}}\n"
        )

    answer = (result.get("answer") or "").strip()
    warnings = result.get("warnings") or []
    facts = result.get("facts") or []
    requires = result.get("requires_verification") or []

    lines = ["h2. Veyra — сверка с корпоративной памятью", ""]
    if answer:
        lines += [answer, ""]

    lines.append("h3. Расхождения и риски")
    if warnings:
        lines.append("|| Находка ||")
        for w in warnings:
            lines.append(f"| {w} |")
    else:
        lines.append("В проверенном объёме расхождений не выявлено.")
    lines.append("")

    if facts:
        lines.append("h3. Источники")
        for f in facts:
            src = f.get("source") or {}
            title = src.get("title", "?")
            section = src.get("section")
            ref = f"{title}{' / ' + section if section else ''}"
            lines.append(f"* {f.get('statement', '')} — _{ref}_")
        lines.append("")

    if requires:
        lines.append("h3. Что проверить")
        for r in requires:
            lines.append(f"* {r}")
        lines.append("")

    cov = (result.get("metadata") or {}).get("coverage") or {}
    if cov:
        lines.append(
            f"_Охват: {cov.get('documents_in_context', '?')} из "
            f"{cov.get('documents_total', '?')} документов, режим "
            f"{cov.get('context_mode', '?')}._"
        )
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    raw = sys.stdin.read()
    if not raw.strip():
        print("Передай JSON-ответ инструмента veyra через stdin")
        sys.exit(1)
    print(build_report(json.loads(raw)))
