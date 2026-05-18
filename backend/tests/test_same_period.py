"""Юнит-тест `_same_period` — без БД и без LLP, ядро фикса числового шума.

Запуск:  cd backend && python -m pytest tests/test_same_period.py -q
Или:     cd backend && python tests/test_same_period.py
"""
from app.skills.find_contradictions import _same_period


def test_both_periods_unknown_not_comparable():
    # Ядро фикса: две метрики без подтверждённого периода НЕ сравниваются.
    # regex-augmented метрики все идут так — раньше давали комбинаторный шум.
    assert _same_period(None, None) is False
    assert _same_period("", "") is False
    assert _same_period("выручка за период", "план продаж") is False


def test_one_period_unknown_not_comparable():
    assert _same_period("2025", None) is False
    assert _same_period(None, "2025") is False


def test_same_year_comparable():
    assert _same_period("2025", "2025") is True


def test_different_year_not_comparable():
    assert _same_period("2024", "2025") is False


def test_same_year_same_quarter():
    assert _same_period("Q1 2025", "2025 Q1") is True


def test_same_year_different_quarter():
    assert _same_period("Q1 2025", "Q2 2025") is False


def test_same_year_different_month():
    assert _same_period("2025-03", "2025-06") is False


def test_year_vs_finer_granularity_same_year():
    # Год известен у обоих, более точная гранулярность есть только у одного —
    # конфликтовать нечему, периоды совместимы.
    assert _same_period("2025", "2025-03") is True


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} passed")
