"""Acceptance gate — прогон 5 размеченных вопросов против запущенного API.

Запуск (сервер должен быть поднят на localhost:8000):
    python scripts/run_gate.py

Сохраняет сырые JSON-ответы в gate-out/ и печатает человекочитаемую сводку.
Только stdlib — никаких зависимостей.
"""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

BASE = "http://localhost:8000"
OUT_DIR = Path(__file__).parent.parent / "gate-out"

# (ключ, режим, вопрос) — режим соответствует ChatMode на бэкенде.
QUESTIONS = [
    ("q1_L01", "contradictions",
     "Как обстоят дела с PRO-сегментом продавцов по итогам 2025 года — "
     "сегмент растёт или падает?"),
    ("q2_N02", "contradictions",
     "Какой churn rate и отток PRO-продавцов заложен в B2C Journey? "
     "Есть ли там внутренние нестыковки в цифрах?"),
    ("q3_P01", "promises",
     "Что обещали по обучающей платформе для продавцов и что с ней сейчас?"),
    ("q4_G01", "gaps",
     "Какие инициативы остались без выделенных ресурсов или владельцев?"),
    ("q5_L02", "contradictions",
     "Avito — это уже платформа №1 для старта бизнеса, или пока только цель? "
     "Что говорят документы?"),
]


def _post(path: str, payload: dict, timeout: int = 240) -> dict:
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _check_server() -> bool:
    try:
        with urllib.request.urlopen(BASE + "/health", timeout=5) as resp:
            resp.read()
        return True
    except urllib.error.URLError as exc:
        print(f"❌ Сервер на {BASE} недоступен: {exc.reason}")
        print("   Подними бэкенд:  cd ~/Veyra/backend && uvicorn app.main:app")
        return False
    except Exception as exc:  # noqa: BLE001
        print(f"❌ /health не ответил: {exc}")
        return False


def _trunc(text: str, n: int = 600) -> str:
    text = (text or "").strip()
    return text if len(text) <= n else text[:n] + " …[обрезано]"


def main() -> int:
    if not _check_server():
        return 1

    OUT_DIR.mkdir(exist_ok=True)
    print(f"Сервер жив. Прогоняю {len(QUESTIONS)} вопросов → {OUT_DIR}\n")

    for key, mode, message in QUESTIONS:
        print("=" * 72)
        print(f"{key}  [режим: {mode}]")
        print(f"Вопрос: {message}")
        print("-" * 72)
        try:
            data = _post("/api/chat", {"message": message, "mode": mode})
        except Exception as exc:  # noqa: BLE001
            print(f"❌ ОШИБКА запроса: {exc}\n")
            continue

        (OUT_DIR / f"{key}.json").write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        print("ОТВЕТ:")
        print(_trunc(data.get("answer", "")))

        facts = data.get("facts") or []
        print(f"\nФАКТЫ ({len(facts)}):")
        for f in facts[:12]:
            src = f.get("source") or {}
            print(f"  • {_trunc(f.get('statement', ''), 200)}")
            print(f"      ← {src.get('title', '?')} / {src.get('section') or '—'}")

        warnings = data.get("warnings") or []
        print(f"\nWARNINGS / РАСХОЖДЕНИЯ ({len(warnings)}):")
        for w in warnings:
            print(f"  ⚠ {w}")

        hyp = data.get("hypotheses") or []
        if hyp:
            print(f"\nГИПОТЕЗЫ ({len(hyp)}):")
            for h in hyp:
                print(f"  • {_trunc(h, 200)}")

        req = data.get("requires_verification") or []
        if req:
            print(f"\nТРЕБУЕТ ПРОВЕРКИ ({len(req)}):")
            for r in req:
                print(f"  ? {_trunc(r, 200)}")

        meta = data.get("metadata") or {}
        print(f"\nmeta: {meta.get('chunks_retrieved', '?')} чанков, "
              f"{meta.get('latency_ms', '?')}ms, "
              f"agents={meta.get('agents_used')}")
        print()

    print("=" * 72)
    print(f"Готово. Сырые ответы — в {OUT_DIR}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
