"""Grounding — программная проверка что утверждение факта реально подтверждено
содержимым чанка-источника.

LLM может выдать факт, который выглядит уверенно, но в исходном чанке его нет.
Это галлюцинация. Эта функция ловит такие случаи через fuzzy-match + проверку
ключевых токенов (числа, имена).
"""
from __future__ import annotations

import difflib
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)


# Числа с единицами — самые проверяемые токены. Должны совпасть точно.
_NUMBER_RE = re.compile(
    r"\d[\d.,]*\s*(?:%|млн|млрд|тыс|k|K|m|M|млрд|RUB|руб|USD|Bn|Mn|FTE|x|кв|points?|пункт\w*)?",
    re.IGNORECASE,
)

# Собственные имена / организации / продукты — слова с заглавной буквы.
_PROPER_NAME_RE = re.compile(
    r"\b(?:[А-ЯЁ][а-яё]+(?:[\s-][А-ЯЁ][а-яё]+){0,3}"
    r"|[A-Z][a-z]+(?:[\s-][A-Z][a-z]+){0,3}"
    r"|[A-Z]{2,}(?:[\s-][A-Z][a-z]+){0,2})"
    r"\b"
)


def _normalize_number(token: str) -> str:
    """«4,2 млрд» / «4.2 bln» → '4.2'. Помогает сравнивать кросс-формат."""
    t = token.lower().replace(",", ".").strip()
    m = re.search(r"\d+(?:\.\d+)?", t)
    return m.group(0) if m else t


def extract_key_tokens(statement: str) -> tuple[set[str], set[str]]:
    """Возвращает (числа, имена) — то что должно встречаться в чанке если
    утверждение подтверждается им."""
    numbers = {_normalize_number(m.group()) for m in _NUMBER_RE.finditer(statement)}
    numbers = {n for n in numbers if n}
    names = set()
    for m in _PROPER_NAME_RE.finditer(statement):
        token = m.group().strip()
        # Отбрасываем шумовые имена вроде "Если", "Это", "При"
        if len(token) > 2 and token.lower() not in _NOISE_NAMES:
            names.add(token)
    return numbers, names


_NOISE_NAMES = {
    "если", "это", "при", "для", "после", "перед", "и", "но", "а", "то",
    "the", "this", "that", "if", "and", "or", "as", "in", "on", "at",
    "по", "из", "от", "до", "к", "с", "об", "у", "о",
}


def _fuzzy_substring_ratio(needle: str, haystack: str) -> float:
    """Best fuzzy ratio найбольшего matching block из needle в haystack.
    Подходит для проверки 'есть ли близкая фраза в чанке'."""
    if not needle or not haystack:
        return 0.0
    matcher = difflib.SequenceMatcher(None, needle.lower(), haystack.lower())
    match = matcher.find_longest_match(0, len(needle), 0, len(haystack))
    return match.size / max(1, len(needle))


def is_grounded(
    statement: str,
    chunk_content: str,
    min_token_coverage: float = 0.5,
    min_fuzzy: float = 0.35,
) -> tuple[bool, str]:
    """Проверяет что statement подтверждается чанком. Возвращает (ok, причина)."""
    if not statement or not chunk_content:
        return False, "empty"

    statement_norm = statement.lower().strip()
    chunk_lower = chunk_content.lower()

    # Очень короткие утверждения проверяем по прямому substring + fuzzy.
    # Раньше отбрасывали при отсутствии прямого вхождения — слишком жёстко
    # на парафразах вроде "TRI*M -12 пунктов" vs "TRI*M has decreased by 12
    # points".
    if len(statement_norm) < 25:
        if statement_norm in chunk_lower:
            return True, "direct-substring"
        ratio = _fuzzy_substring_ratio(statement, chunk_content)
        if ratio >= min_fuzzy:
            return True, f"short-fuzzy {ratio:.2f}"
        return False, f"short-not-found (fuzzy {ratio:.2f})"

    # Числа — если есть, должны совпасть (precision важна больше)
    numbers, names = extract_key_tokens(statement)
    if numbers:
        found_numbers = sum(1 for n in numbers if n in chunk_lower)
        if found_numbers / len(numbers) < 0.5:
            return False, f"numbers-mismatch ({found_numbers}/{len(numbers)})"

    # Имена — должна совпасть хотя бы половина
    if names:
        found_names = sum(1 for n in names if n.lower() in chunk_lower)
        if found_names / len(names) < min_token_coverage:
            # Имён мало — добиваем fuzzy-проверкой
            ratio = _fuzzy_substring_ratio(statement, chunk_content)
            if ratio < min_fuzzy:
                return False, f"names-mismatch ({found_names}/{len(names)}) + fuzzy {ratio:.2f}"

    # Нет проверяемых токенов — fallback на fuzzy ratio
    if not numbers and not names:
        ratio = _fuzzy_substring_ratio(statement, chunk_content)
        if ratio < min_fuzzy:
            return False, f"fuzzy {ratio:.2f} < {min_fuzzy}"

    return True, "ok"


def ground_facts(facts_with_chunks: list[tuple[Any, Any]]) -> tuple[list, list, list]:
    """Прогоняет grounding-проверку.

    Вход: список (fact_dict, chunk) где fact_dict имеет ключ 'statement'
    и chunk — RetrievedChunk с .content.

    Возвращает (grounded, unsupported, reasons):
    - grounded: list[(fact_dict, chunk)] — подтверждённые
    - unsupported: list[(fact_dict, chunk, reason)] — непрошедшие
    - reasons: список строк-причин для логирования
    """
    grounded = []
    unsupported = []
    reasons: list[str] = []
    for fact, chunk in facts_with_chunks:
        statement = fact.get("statement", "") if isinstance(fact, dict) else getattr(fact, "statement", "")
        content = getattr(chunk, "content", "") if chunk else ""
        ok, reason = is_grounded(statement, content)
        if ok:
            grounded.append((fact, chunk))
        else:
            unsupported.append((fact, chunk, reason))
            reasons.append(f"{reason}: {statement[:80]}...")
    if unsupported:
        logger.info("grounding: %d/%d facts unsupported", len(unsupported), len(facts_with_chunks))
        for r in reasons[:5]:
            logger.debug("  - %s", r)
    return grounded, unsupported, reasons
