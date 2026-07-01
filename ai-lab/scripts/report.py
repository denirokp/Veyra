"""Сборка Confluence-страницы по результату разбора AI Lab.

Заголовок + ответ + таблица расхождений + источники. Только stdlib.
Скрипт ничего не вызывает и не рассуждает — он форматирует структуру
разбора, которую собрал Claude (данные ai-lab-mcp + его рассуждение).

Вход (stdin): JSON
{answer, facts[], warnings[], hypotheses[], requires_verification[], metadata, error}.
metadata.coverage — охват (documents_in_context / documents_total /
context_mode / last_indexed_at).

Валидация входа СТРОГАЯ: любой неизвестный ключ верхнего уровня — почти
всегда опечатка (`warning` вместо `warnings`), из-за которой раздел тихо
терялся. Скрипт падает громко (exit != 0), а не молча отдаёт пустой отчёт.
"""
from __future__ import annotations

import json
import sys

KNOWN_KEYS = {
    "answer", "facts", "warnings", "hypotheses",
    "requires_verification", "metadata", "error",
}
LIST_KEYS = ("facts", "warnings", "hypotheses", "requires_verification")


def _validate(result: dict) -> None:
    if not isinstance(result, dict):
        raise SystemExit("report.py: ожидался JSON-объект на входе")
    unknown = sorted(set(result) - KNOWN_KEYS)
    if unknown:
        raise SystemExit(
            "report.py: неизвестные ключи верхнего уровня (опечатка?): "
            + ", ".join(unknown)
            + "\n  допустимые: " + ", ".join(sorted(KNOWN_KEYS))
        )
    for key in LIST_KEYS:
        if key in result and not isinstance(result[key], list):
            raise SystemExit(f"report.py: ключ '{key}' должен быть списком")


def _source_ref(fact: dict) -> str:
    src = fact.get("source") or {}
    ref = src.get("title", "?")
    if src.get("section"):
        ref += " / " + src["section"]
    return ref


def build_report(result: dict) -> str:
    if result.get("error"):
        return ("h2. AI Lab — отчёт\n\n"
                f"{{warning}}AI Lab недоступна: {result['error']}{{warning}}\n")

    answer = (result.get("answer") or "").strip()
    warnings = result.get("warnings") or []
    facts = result.get("facts") or []
    requires = result.get("requires_verification") or []

    lines = ["h2. AI Lab — сверка с корпоративной памятью", ""]
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
            lines.append(f"* {f.get('statement', '')} — _{_source_ref(f)}_")
        lines.append("")

    if requires:
        lines.append("h3. Что проверить")
        for r in requires:
            lines.append(f"* {r}")
        lines.append("")

    cov = (result.get("metadata") or {}).get("coverage") or {}
    if cov:
        fresh = cov.get("last_indexed_at")
        tail = f", данные на {fresh}" if fresh else ""
        lines.append(
            f"_Охват: {cov.get('documents_in_context', '?')} из "
            f"{cov.get('documents_total', '?')} документов, режим "
            f"{cov.get('context_mode', '?')}{tail}._"
        )
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    raw = sys.stdin.read()
    if not raw.strip():
        raise SystemExit("Передай JSON-ответ инструмента ai-lab через stdin")
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"report.py: невалидный JSON на входе: {exc}")
    _validate(parsed)
    print(build_report(parsed))
