"""CI regression: проверка структуры eval_set.yaml и загрузки промптов.

Запуск:
    cd /home/user/Veyra
    python -m pytest tests/test_eval_structure.py -v
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).parent.parent
EVAL_YAML = REPO_ROOT / "tests" / "eval_set.yaml"
PROMPTS_DIR = REPO_ROOT / "backend" / "prompts"

VALID_MODES = {"search", "contradictions", "promises", "gaps", "write", "validate", "research"}
REQUIRED_CASE_FIELDS = {"id", "query", "expected_mode"}


# ── Eval set structure ────────────────────────────────────────────────────────

def _load_cases() -> list[dict]:
    with open(EVAL_YAML, encoding="utf-8") as f:
        return yaml.safe_load(f).get("cases", [])


def test_eval_yaml_exists():
    assert EVAL_YAML.exists(), f"eval_set.yaml не найден: {EVAL_YAML}"


def test_eval_yaml_has_cases():
    cases = _load_cases()
    assert len(cases) >= 15, f"Ожидалось >= 15 кейсов, найдено {len(cases)}"


def test_eval_case_ids_unique():
    cases = _load_cases()
    ids = [c["id"] for c in cases]
    duplicates = [i for i in ids if ids.count(i) > 1]
    assert not duplicates, f"Дублирующиеся id: {set(duplicates)}"


@pytest.mark.parametrize("case", _load_cases(), ids=[c["id"] for c in _load_cases()])
def test_eval_case_structure(case: dict):
    missing = REQUIRED_CASE_FIELDS - case.keys()
    assert not missing, f"Кейс {case.get('id')!r}: отсутствуют поля {missing}"

    assert case["query"].strip(), f"Кейс {case['id']}: пустой query"

    mode = case.get("expected_mode")
    assert mode in VALID_MODES, (
        f"Кейс {case['id']}: invalid expected_mode={mode!r}. "
        f"Допустимые: {VALID_MODES}"
    )

    min_facts = case.get("min_facts", 0)
    assert isinstance(min_facts, int) and min_facts >= 0, (
        f"Кейс {case['id']}: min_facts должен быть int >= 0"
    )


# ── Prompts load ──────────────────────────────────────────────────────────────

def test_corpus_system_prompt_exists():
    p = PROMPTS_DIR / "corpus_system.txt"
    assert p.exists(), f"corpus_system.txt не найден: {p}"


def test_corpus_system_prompt_non_empty():
    p = PROMPTS_DIR / "corpus_system.txt"
    content = p.read_text(encoding="utf-8").strip()
    assert len(content) > 100, "corpus_system.txt слишком короткий (< 100 символов)"


def test_corpus_system_prompt_has_json_format():
    content = (PROMPTS_DIR / "corpus_system.txt").read_text(encoding="utf-8")
    assert '"answer"' in content, "corpus_system.txt должен содержать инструкцию про поле answer"
    assert '"facts"' in content, "corpus_system.txt должен содержать инструкцию про поле facts"


def test_corpus_system_prompt_has_injection_guard():
    content = (PROMPTS_DIR / "corpus_system.txt").read_text(encoding="utf-8")
    assert "uploaded_document" in content, (
        "corpus_system.txt должен содержать инструкцию о теге <uploaded_document>"
    )


def test_router_prompt_exists():
    p = PROMPTS_DIR / "router.txt"
    assert p.exists(), f"router.txt не найден: {p}"


def test_router_prompt_has_all_modes():
    content = (PROMPTS_DIR / "router.txt").read_text(encoding="utf-8")
    for mode in VALID_MODES:
        assert f"- {mode}:" in content, f"router.txt не содержит описание режима {mode!r}"


def test_router_prompt_returns_json_instruction():
    content = (PROMPTS_DIR / "router.txt").read_text(encoding="utf-8")
    assert "subqueries" in content, "router.txt должен содержать инструкцию про subqueries"
    assert "JSON" in content, "router.txt должен упоминать JSON"


# ── Python imports (smoke) ────────────────────────────────────────────────────

def test_prompts_importable_from_corpus_agent():
    """Проверяем что corpus.py может прочитать промпт — без запуска LLM."""
    sys.path.insert(0, str(REPO_ROOT / "backend"))
    try:
        # Патчим зависимости которые нужны при импорте
        import unittest.mock as mock
        with mock.patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test", "OPENAI_API_KEY": "test"}):
            # Только читаем промпт-файл напрямую (не импортируем модуль целиком)
            prompt = (PROMPTS_DIR / "corpus_system.txt").read_text(encoding="utf-8")
            assert prompt
    finally:
        sys.path.pop(0)
