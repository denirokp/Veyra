"""Перепроверка числового детектора по УЖЕ проиндексированной базе.

Переиндексации НЕ требует и LLM НЕ вызывает. Берёт метрики-сущности,
которые уже лежат в khronika.db, и заново прогоняет по ним детерминированную
логику find_contradictions. Так фикс `_same_period` проверяется на том же
корпусе, что дал 162 находки, без повторного прогона index_docs.py.

База только читается — ничего не пишет и не удаляет.

  python scripts/retest_numeric.py

Вывод: сколько пар детектор флагует СЕЙЧАС и сколько пар подавил именно
из-за нового правила «период не подтверждён → пропускаем».
"""
import asyncio
import os
import sys
from collections import Counter, defaultdict
from itertools import combinations
from pathlib import Path

BACKEND_DIR = Path(__file__).parent.parent / "backend"
sys.path.insert(0, str(BACKEND_DIR))
os.chdir(BACKEND_DIR)

from sqlalchemy import select  # noqa: E402

from app.skills.find_contradictions import (  # noqa: E402
    _canonical,
    _parse_period,
    _same_period,
    _severity,
    _values_differ,
)
from app.storage.sql_db import Document, Entity, engine  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402


async def main() -> None:
    async with AsyncSession(engine) as db:
        titles = {
            d.id: d.title
            for d in (await db.execute(select(Document))).scalars()
        }
        metrics = [
            e for e in (await db.execute(
                select(Entity).where(Entity.type == "metric")
            )).scalars()
        ]

    by_name: dict[str, list[Entity]] = defaultdict(list)
    for e in metrics:
        norm = (e.normalized_name or "").strip()
        if norm:
            by_name[norm].append(e)

    flagged = 0
    suppressed_noperiod = 0   # обе метрики без периода — это и есть удалённый шум
    suppressed_period = 0     # период есть, но не совпал (старый код тоже подавлял)
    per_doc: Counter = Counter()
    severities: Counter = Counter()
    flagged_pairs: list[dict] = []

    for norm, group in by_name.items():
        for a, b in combinations(group, 2):
            canon_a = _canonical(a.value, a.unit)
            canon_b = _canonical(b.value, b.unit)
            if canon_a is None or canon_b is None:
                continue
            (val_a, kind_a), (val_b, kind_b) = canon_a, canon_b
            if kind_a != kind_b:
                continue
            if not _values_differ(val_a, val_b):
                continue

            date_a = str(a.date_context or "")
            date_b = str(b.date_context or "")
            if _same_period(date_a, date_b):
                flagged += 1
                severities[_severity(val_a, val_b)] += 1
                per_doc[a.document_id] += 1
                if b.document_id != a.document_id:
                    per_doc[b.document_id] += 1
                flagged_pairs.append({
                    "norm": norm,
                    "name_a": a.name, "value_a": a.value, "unit_a": a.unit,
                    "name_b": b.name, "value_b": b.value, "unit_b": b.unit,
                    "period_a": date_a or "—", "period_b": date_b or "—",
                    "severity": _severity(val_a, val_b),
                    "same_doc": a.document_id == b.document_id,
                    "doc": titles.get(a.document_id, a.document_id)[:48],
                })
            elif _parse_period(date_a)[0] is None and _parse_period(date_b)[0] is None:
                suppressed_noperiod += 1
            else:
                suppressed_period += 1

    old_total = flagged + suppressed_noperiod
    print("=" * 60)
    print(f"Метрик в базе:                 {len(metrics)}")
    print(f"Уникальных имён метрик:        {len(by_name)}")
    print("-" * 60)
    print(f"Флагуется СЕЙЧАС (с фиксом):    {flagged}")
    print(f"Подавлено фиксом (период None): {suppressed_noperiod}")
    print(f"= было бы до фикса:            {old_total}")
    print(f"(подавлено по несовпавшему периоду, старый код тоже: {suppressed_period})")
    print("-" * 60)
    print("Severity флагованных:", dict(severities))
    print("-" * 60)
    print("По документам (флагованных пар, top-15):")
    for doc_id, n in per_doc.most_common(15):
        print(f"  {n:4d}  {titles.get(doc_id, doc_id)[:60]}")
    print("=" * 60)

    if "--dump" in sys.argv:
        print("\nФЛАГОВАННЫЕ ПАРЫ (все):")
        flagged_pairs.sort(key=lambda p: (p["doc"], p["norm"]))
        for p in flagged_pairs:
            scope = "intra" if p["same_doc"] else "cross"
            print(f"\n  [{p['severity']:8}] [{scope}] {p['doc']}")
            print(f"    norm='{p['norm']}'")
            print(f"    A: {p['value_a']} {p['unit_a'] or ''}  «{p['name_a']}»  ({p['period_a']})")
            print(f"    B: {p['value_b']} {p['unit_b'] or ''}  «{p['name_b']}»  ({p['period_b']})")


if __name__ == "__main__":
    asyncio.run(main())
