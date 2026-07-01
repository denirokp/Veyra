"""Серверная тематическая фильтрация строк find_* по запросу.

Раньше навык тянул всю таблицу расхождений/обещаний и фильтровал её «на
глаз» в LLM — на 2000 строках это промахивалось. Здесь фильтрация делается
на сервере детерминированно: строка релевантна, если её текст содержит
токены темы запроса; сортируем по числу совпавших токенов.

Не эмбеддинги (их прогон по всем строкам на живом пути дорог) — токен-матч
по тексту строки. Клонит к recall: лучше вернуть чуть лишнего, чем потерять
находку; финальный отбор всё равно за моделью.
"""
from __future__ import annotations

import re
from typing import Callable

_TOKEN_RE = re.compile(r"[^\W_]+", re.UNICODE)

# Частые служебные слова RU/EN — не должны «матчить» пол-таблицы.
_STOP = {
    "что", "как", "для", "или", "это", "нет", "все", "уже", "при", "под",
    "над", "про", "без", "the", "and", "for", "are", "not", "you", "with",
    "есть", "быть", "между", "если", "чтобы",
}


def _tokens(text: str) -> list[str]:
    return [
        t.lower()
        for t in _TOKEN_RE.findall(text or "")
        if len(t) >= 3 and t.lower() not in _STOP
    ]


def filter_rows_by_query(
    rows: list[dict],
    query: str | None,
    text_of: Callable[[dict], str],
    relevant_doc_ids: set[str] | None = None,
    doc_ids_of: Callable[[dict], tuple[str, ...]] | None = None,
) -> list[dict]:
    """Отобрать строки find_*, релевантные теме `query`.

    query пустой/None → вернуть строки как есть. Иначе строка проходит по
    ЛЮБОМУ из двух сигналов:
      1) токен-матч — токен запроса (≥3 симв., без стоп-слов) встречается
         подстрокой в тексте строки (`text_of`);
      2) семантика — документ строки попал в `relevant_doc_ids` (их отдаёт
         ретривер по эмбеддингам, `doc_ids_of` достаёт id доков из строки).
    Второй сигнал ловит синонимы («выручка» → строки с «GMV / оборот»),
    которых буквальный токен-матч не находит. Ранжируем: токен-хиты вперёд,
    семантическое совпадение добавляет полбалла.
    """
    if not query or not query.strip():
        return rows
    terms = set(_tokens(query))
    rel = relevant_doc_ids or set()
    if not terms and not rel:
        return rows

    scored: list[tuple[float, int, dict]] = []
    for i, row in enumerate(rows):
        hay = (text_of(row) or "").lower()
        hits = sum(1 for t in terms if t in hay)
        docmatch = bool(rel and doc_ids_of and any(d in rel for d in doc_ids_of(row)))
        if hits or docmatch:
            score = hits + (0.5 if docmatch else 0.0)
            scored.append((score, -i, row))  # -i: стабильный порядок при равенстве
    scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
    return [row for _, _, row in scored]
