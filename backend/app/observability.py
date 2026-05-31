"""G6 — наблюдаемость: учёт стоимости LLM и числа вызовов.

Лёгкий in-process аккумулятор. Не претендует на Prometheus/Redash — это
MVP-слой: считает токены и стоимость на каждый call_llm, отдаёт снимок
через GET /api/metrics/usage. Сбрасывается при рестарте процесса;
долговременная агрегация — задача внешнего Redash (см. api/metrics.py).

Стоимость считается по ценам из settings (USD за 1М токенов). Если цены
не заданы (0) — копим только токены, $ остаётся 0. Намеренно: лучше
честный ноль, чем выдуманная цена под чужого провайдера.
"""
from __future__ import annotations

import logging
import threading
from collections import defaultdict
from dataclasses import dataclass

from app.settings import settings

logger = logging.getLogger(__name__)

# call_llm — async (один loop), но embed гоняет encode в thread'ах; lock дёшев
# и снимает любые сомнения по гонкам при будущих изменениях.
_lock = threading.Lock()


@dataclass
class _ModelStat:
    calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_usd: float = 0.0


_stats: dict[str, _ModelStat] = defaultdict(_ModelStat)


def _cost(prompt_tokens: int, completion_tokens: int) -> float:
    return (
        prompt_tokens / 1_000_000 * settings.LLM_PRICE_INPUT_PER_1M
        + completion_tokens / 1_000_000 * settings.LLM_PRICE_OUTPUT_PER_1M
    )


def record_llm_usage(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    """Учитывает один LLM-вызов. Возвращает его стоимость в USD (0 если цены не заданы)."""
    cost = _cost(prompt_tokens, completion_tokens)
    with _lock:
        s = _stats[model]
        s.calls += 1
        s.prompt_tokens += prompt_tokens
        s.completion_tokens += completion_tokens
        s.cost_usd += cost
    logger.info(
        "llm_usage model=%s prompt=%d completion=%d cost=$%.4f",
        model, prompt_tokens, completion_tokens, cost,
    )
    return cost


def snapshot() -> dict:
    """Снимок накопленных метрик с момента старта процесса."""
    with _lock:
        by_model = {
            name: {
                "calls": s.calls,
                "prompt_tokens": s.prompt_tokens,
                "completion_tokens": s.completion_tokens,
                "total_tokens": s.prompt_tokens + s.completion_tokens,
                "cost_usd": round(s.cost_usd, 6),
            }
            for name, s in _stats.items()
        }
    totals = {
        "calls": sum(m["calls"] for m in by_model.values()),
        "prompt_tokens": sum(m["prompt_tokens"] for m in by_model.values()),
        "completion_tokens": sum(m["completion_tokens"] for m in by_model.values()),
        "total_tokens": sum(m["total_tokens"] for m in by_model.values()),
        "cost_usd": round(sum(m["cost_usd"] for m in by_model.values()), 6),
    }
    cost_priced = settings.LLM_PRICE_INPUT_PER_1M > 0 or settings.LLM_PRICE_OUTPUT_PER_1M > 0
    return {"totals": totals, "by_model": by_model, "cost_priced": cost_priced}


def reset() -> None:
    """Сброс счётчиков (для тестов / ручного обнуления пилота)."""
    with _lock:
        _stats.clear()
