"""Skill: find_contradictions — детерминированный поиск числовых расхождений.

БЕЗ LLM. Сравнивает метрики-сущности (таблица Entity) попарно: одна и та же
метрика (точное совпадение нормализованного имени) с разными значениями в
совместимый период и при сопоставимой размерности → числовое расхождение.

Покрывает И кросс-документные, И внутридокументные расхождения: сущность из
того же документа сравнивается так же, как из другого.

Принцип — precision важнее recall. При любой неоднозначности (не удалось
распарсить значение или единицу, не совпали период или размерность) пара
пропускается. Имя с ≥3 значениями в один период — перегружено (таблица или
точки траектории), не флагуется. Чего детектор не поймал — найдёт Claude.

Старая схема (LLM-зависимая + fuzzy-матч имён по обрезкам контекста) давала
precision 11% на валидации: фабриковала значения, не нормализовала единицы,
склеивала разные периоды. Переписано на эту детерминированную схему.
"""
from __future__ import annotations

import logging
import re
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.storage.sql_db import Entity, NumericContradiction

logger = logging.getLogger(__name__)

# Относительный допуск: расхождение меньше — это округление, не противоречие.
REL_TOLERANCE = 0.02

# Под одним именем в совместимый период ≥ этого числа разных значений —
# имя перегружено (таблица-разбивка/точки траектории), пары не флагуются.
OVERLOADED_NAME_MIN_VALUES = 3


# ── Парсинг числового значения ────────────────────────────────────────────────

def _parse_number(raw) -> float | None:
    """Достаёт число из строки. '4,2'→4.2, '1 234'→1234, '~33.3'→33.3.
    None — если числа нет."""
    if raw is None:
        return None
    s = str(raw).strip().lower().replace(" ", " ")
    if not s:
        return None
    # пробел как разделитель тысяч между цифрами → убрать
    s = re.sub(r"(?<=\d)[  ](?=\d)", "", s)
    s = s.replace(",", ".")
    m = re.search(r"[-+]?\d+(?:\.\d+)?", s)
    if not m:
        return None
    try:
        return float(m.group())
    except ValueError:
        return None


# ── Размерность и масштаб единицы ─────────────────────────────────────────────

# Множители масштаба по подстроке; длинные раньше коротких.
_SCALE_TOKENS = (
    ("млрд", 1e9), ("billion", 1e9), ("bln", 1e9),
    ("млн", 1e6), ("mln", 1e6), ("mio", 1e6),
    ("тыс", 1e3), ("thousand", 1e3),
)


def _unit_kind_scale(unit) -> tuple[str, float] | None:
    """(kind, scale) или None, если единицу понять нельзя → пара пропускается.

    kind: percent | currency | count | multiplier | points | amount | number.
    Сопоставимы только сущности с одинаковым kind.
    """
    u = (str(unit) if unit is not None else "").strip().lower()
    if not u:
        return ("number", 1.0)

    if "%" in u or "п.п" in u or u in ("пп", "pp") or "percent" in u or "процент" in u:
        return ("percent", 1.0)

    # масштаб
    scale = 1.0
    for tok, mult in _SCALE_TOKENS:
        if tok in u:
            scale = mult
            break
    else:
        if re.search(r"\b(bn|b)\b", u):
            scale = 1e9
        elif re.search(r"\b(mn|m)\b", u):
            scale = 1e6
        elif re.search(r"\bk\b", u):
            scale = 1e3

    # валютные формы вида BR / MR / KR / blnR / mRUB / RUB
    compact = u.replace(" ", "").replace(".", "")
    m = re.fullmatch(r"(bln|mln|b|m|k)?r(ub)?", compact)
    if m:
        scale = {"bln": 1e9, "b": 1e9, "mln": 1e6, "m": 1e6,
                 "k": 1e3}.get(m.group(1), scale)
        return ("currency", scale)

    if any(t in u for t in ("руб", "rub", "₽", "usd", "долл", "eur")):
        return ("currency", scale)
    if any(t in u for t in ("fte", "чел", "штат", "employee", "headcount")):
        return ("count", scale)
    if any(t in u for t in ("раз", "кратн", "times")) or re.search(r"\bx\b", u):
        return ("multiplier", scale)
    if any(t in u for t in ("пункт", "point", "score", "балл")):
        return ("points", scale)
    if any(t in u for t in ("шт", "штук", "unit", "item")):
        return ("count", scale)

    # масштаб понятен, размерность — нет: сопоставимо только с таким же amount
    if scale != 1.0:
        return ("amount", scale)
    # единицу не распознали — не флагуем
    return None


def _canonical(value, unit) -> tuple[float, str] | None:
    """(каноническое_число, kind) или None, если пару нельзя сравнивать."""
    num = _parse_number(value)
    if num is None:
        return None
    ks = _unit_kind_scale(unit)
    if ks is None:
        return None
    kind, scale = ks
    return (num * scale, kind)


def _values_differ(a: float, b: float) -> bool:
    """True если значения расходятся больше допуска (не округление)."""
    if a == b:
        return False
    denom = max(abs(a), abs(b))
    if denom == 0:
        return False
    return abs(a - b) / denom > REL_TOLERANCE


def _severity(a: float, b: float) -> str:
    """Критичность числового расхождения по СТРОГОМУ правилу — величине
    отрыва значений (не оценка «на глаз»). Чем сильнее расходятся, тем
    выше шанс реальной ошибки, которую читатель примет за провал."""
    denom = max(abs(a), abs(b))
    if denom == 0:
        return "low"
    rel = abs(a - b) / denom
    if rel >= 0.5:
        return "critical"
    if rel >= 0.15:
        return "medium"
    return "low"


# ── Парсер периодов ───────────────────────────────────────────────────────────

_QUARTER_RE = re.compile(
    r"q\s*([1-4])\s*[/\-' ]?\s*(\d{2,4})|(\d{2,4})\s*[/\-' ]?\s*q\s*([1-4])",
    re.IGNORECASE,
)
_MONTH_RU = {
    "январ": 1, "феврал": 2, "март": 3, "апрел": 4, "ма": 5, "июн": 6,
    "июл": 7, "август": 8, "сентябр": 9, "октябр": 10, "ноябр": 11, "декабр": 12,
}


def _parse_period(value: str | None) -> tuple[int | None, int | None, int | None]:
    """(year, quarter, month). Любое поле может быть None.
    Поддерживает '2025', '2025-03', '2025-03-15', 'Q1 2025', '2025 Q1',
    'март 2025'."""
    if not value:
        return (None, None, None)
    s = str(value).strip().lower()

    m = re.match(r"^(\d{4})(?:[-/](\d{1,2})(?:[-/](\d{1,2}))?)?$", s)
    if m:
        year = int(m.group(1))
        month = int(m.group(2)) if m.group(2) else None
        quarter = (month - 1) // 3 + 1 if month else None
        return (year, quarter, month)

    m = _QUARTER_RE.search(s)
    if m:
        q = int(m.group(1) or m.group(4))
        y = int(m.group(2) or m.group(3))
        if y < 100:
            y += 2000
        return (y, q, None)

    year_match = re.search(r"(\d{4})", s)
    year = int(year_match.group(1)) if year_match else None
    for prefix, month in _MONTH_RU.items():
        if prefix in s:
            return (year, (month - 1) // 3 + 1, month)

    if year:
        return (year, None, None)
    return (None, None, None)


def _same_period(date_a: str | None, date_b: str | None) -> bool:
    """True только если периоды точно совместимы.

    Период подтверждён НЕ у обеих метрик → False. regex-augmented метрики
    все идут без периода (`date_context=None`); если бы безпериодные пары
    флагувались, две метрики с совпавшим именем из РАЗНЫХ лет (год не
    распознан) давали бы ложное расхождение — корпус из 28 документов дал
    так десятки шумовых пар на документ. Неоднозначность с периодом → пара
    пропускается (принцип precision-first, см. шапку файла).
    Оба известны → должны совпасть по самой точной общей гранулярности.
    """
    ya, qa, ma = _parse_period(date_a)
    yb, qb, mb = _parse_period(date_b)
    a_known, b_known = ya is not None, yb is not None

    if not (a_known and b_known):
        return False
    if ya != yb:
        return False
    if ma is not None and mb is not None:
        return ma == mb
    if qa is not None and qb is not None:
        return qa == qb
    return True


# ── Поиск ─────────────────────────────────────────────────────────────────────

async def _same_name_metrics(db: AsyncSession, normalized_name: str) -> list[Entity]:
    """Все метрики-сущности с ТОЧНО таким нормализованным именем (вкл. свой
    документ — для внутридокументных расхождений). Никакого fuzzy: обрезки
    контекста в именах regex-метрик делали fuzzy-матч источником ложных пар."""
    result = await db.execute(
        select(Entity).where(
            Entity.type == "metric",
            Entity.normalized_name == normalized_name,
        )
    )
    return list(result.scalars().all())


async def check_and_save_contradictions(
    new_metrics: list[dict],
    new_document_id: str,
    db: AsyncSession,
) -> list[dict]:
    """Детерминированно сравнивает метрики документа со всеми метриками корпуса
    (включая сам документ). Подтверждённые числовые расхождения пишет в
    contradictions. Возвращает список находок."""
    found: list[dict] = []
    seen_pairs: set[frozenset] = set()

    for metric in new_metrics:
        normalized = (metric.get("normalized_name") or "").strip()
        if not normalized:
            continue
        canon_a = _canonical(metric.get("value"), metric.get("unit"))
        if canon_a is None:
            continue
        value_a, kind_a = canon_a
        metric_id = metric.get("id")

        same_name = await _same_name_metrics(db, normalized)

        # Гард перегруженного имени. Если под одним нормализованным именем в
        # совместимый период и с той же размерностью набирается ≥3 РАЗНЫХ
        # значения — это таблица-разбивка или точки траектории (десятки
        # ячеек «GMV CY'23» по категориям, ramp плана 1.2→1.7→…→8), а не
        # пара противоречащих чисел. На корпусе 28 документов так набегало
        # 54 ложные пары. Перегруженное имя → пропускаем целиком.
        cluster = {value_a}
        for other in same_name:
            if other.id == metric_id:
                continue
            canon_o = _canonical(other.value, other.unit)
            if canon_o is None or canon_o[1] != kind_a:
                continue
            if _same_period(metric.get("date_context"),
                            str(other.date_context or "")):
                cluster.add(canon_o[0])
        if len(cluster) >= OVERLOADED_NAME_MIN_VALUES:
            continue

        for existing in same_name:
            if existing.id == metric_id:
                continue  # сама с собой
            pair = frozenset((metric_id, existing.id))
            if pair in seen_pairs:
                continue

            canon_b = _canonical(existing.value, existing.unit)
            if canon_b is None:
                continue
            value_b, kind_b = canon_b
            if kind_a != kind_b:
                continue  # разные размерности — это разные метрики
            if not _same_period(metric.get("date_context"),
                                str(existing.date_context or "")):
                continue
            if not _values_differ(value_a, value_b):
                continue  # совпадают в пределах допуска — округление, не конфликт

            seen_pairs.add(pair)
            found.append({
                "id": str(uuid.uuid4()),
                "metric": metric["name"],
                "value_a": str(metric.get("value")),
                "value_b": str(existing.value),
                "document_id_a": new_document_id,
                "document_id_b": existing.document_id,
                "period": metric.get("date_context"),
                "severity": _severity(value_a, value_b),
                "status": "open",
            })

    # Сохраняем одним commit в конце. Коммитить в цикле нельзя: commit в
    # async-сессии обнуляет (expire) ORM-объекты Entity, и следующий доступ
    # к existing.* падает с MissingGreenlet.
    for row in found:
        db.add(NumericContradiction(**row))
    if found:
        await db.commit()
        logger.info("find_contradictions doc=%s → %d числовых расхождений",
                     new_document_id[:8], len(found))
    return found
