"""Acceptance gate — прогон размеченных вопросов против запущенного API.

Запуск (сервер на localhost:8000):
    python scripts/run_gate.py                # все вопросы, 1 прогон
    python scripts/run_gate.py --runs 3       # 3 прогона, усреднение (ТЗ §13.8)
    python scripts/run_gate.py --retrieval    # форсить retrieval-путь (Фаза 1.5)
    python scripts/run_gate.py q5_L02         # только указанные вопросы

Сверяет ответы с scripts/gate_ground_truth.json и считает recall по трекам.
Precision не автоматизируется — её оценивает человек по warnings/drop-rate.
Только stdlib.
"""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

BASE = "http://localhost:8000"
OUT_DIR = Path(__file__).parent.parent / "gate-out"
GT_PATH = Path(__file__).parent / "gate_ground_truth.json"

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


def _answer_blob(data: dict) -> str:
    """Весь текст ответа одной строкой — для сверки с ground truth."""
    parts = [data.get("answer", "")]
    parts += [f.get("statement", "") for f in data.get("facts") or []]
    parts += data.get("warnings") or []
    parts += data.get("hypotheses") or []
    parts += data.get("requires_verification") or []
    return " ".join(parts).lower()


def _score(key: str, data: dict, gt: dict):
    """Возвращает (hit: bool|None, matched_group). None — нет разметки."""
    spec = gt.get(key)
    if not spec:
        return None, None
    blob = _answer_blob(data)
    for group in spec["any_of"]:
        if all(tok.lower() in blob for tok in group):
            return True, group
    return False, None


def _print_detail(key: str, mode: str, message: str, data: dict) -> None:
    print("=" * 72)
    print(f"{key}  [режим: {mode}]")
    print(f"Вопрос: {message}")
    print("-" * 72)
    print("ОТВЕТ:")
    print(_trunc(data.get("answer", "")))
    facts = data.get("facts") or []
    print(f"\nФАКТЫ ({len(facts)}):")
    for f in facts[:12]:
        src = f.get("source") or {}
        print(f"  • {_trunc(f.get('statement', ''), 200)}")
        print(f"      ← {src.get('title', '?')} / {src.get('section') or '—'}")
    warnings = data.get("warnings") or []
    print(f"\nWARNINGS ({len(warnings)}):")
    for w in warnings:
        print(f"  ⚠ {w}")
    meta = data.get("metadata") or {}
    cov = meta.get("coverage") or {}
    print(f"\nmeta: {meta.get('chunks_retrieved', '?')} чанков, "
          f"{meta.get('latency_ms', '?')}ms, "
          f"режим={cov.get('context_mode', '?')}, "
          f"охват={cov.get('documents_in_context', '?')}/{cov.get('documents_total', '?')} док, "
          f"факты {meta.get('facts_kept', '?')}✓/{meta.get('facts_dropped', '?')}✗")
    print()


def main() -> int:
    if not _check_server():
        return 1

    # --- разбор аргументов ---
    runs = 1
    force_retrieval = False
    keys: list[str] = []
    argv = sys.argv[1:]
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--runs" and i + 1 < len(argv):
            runs = max(1, int(argv[i + 1]))
            i += 2
        elif a == "--retrieval":
            force_retrieval = True
            i += 1
        else:
            keys.append(a)
            i += 1

    questions = [q for q in QUESTIONS if not keys or q[0] in keys]
    if keys and not questions:
        valid = ", ".join(q[0] for q in QUESTIONS)
        print(f"Неизвестные ключи {keys}. Доступны: {valid}")
        return 1

    gt = json.loads(GT_PATH.read_text(encoding="utf-8"))
    OUT_DIR.mkdir(exist_ok=True)
    print(f"Сервер жив. {len(questions)} вопрос(ов) × {runs} прогон(ов)"
          f"{' · retrieval-режим' if force_retrieval else ''} → {OUT_DIR}\n")

    # results[key] = список hit (bool|None) по прогонам
    results: dict[str, list] = {q[0]: [] for q in questions}

    for run_no in range(1, runs + 1):
        if runs > 1:
            print(f"\n########## ПРОГОН {run_no}/{runs} ##########\n")
        for key, mode, message in questions:
            payload = {"message": message, "mode": mode,
                       "force_retrieval": force_retrieval}
            try:
                data = _post("/api/chat", payload)
            except Exception as exc:  # noqa: BLE001
                print(f"{key}: ❌ ОШИБКА запроса: {exc}")
                results[key].append(False)
                continue
            (OUT_DIR / f"{key}.run{run_no}.json").write_text(
                json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            hit, group = _score(key, data, gt)
            results[key].append(hit)
            if run_no == 1:
                _print_detail(key, mode, message, data)
            mark = "✓ HIT" if hit else ("— нет разметки" if hit is None else "✗ MISS")
            extra = f"  (сматчилось: {group})" if group else ""
            print(f"{key}: {mark}{extra}")

    # --- скоркард ---
    print("\n" + "=" * 72)
    print(f"СКОРКАРД — {runs} прогон(ов)")
    print("=" * 72)
    track_hits: dict[str, list] = {}
    for key, mode, message in questions:
        runs_list = results[key]
        scored = [h for h in runs_list if h is not None]
        hits = sum(1 for h in scored if h)
        spec = gt.get(key, {})
        track = spec.get("track", "?")
        rate = (hits / len(scored)) if scored else 0.0
        track_hits.setdefault(track, []).append(rate)
        finding = spec.get("finding", "?")
        bar = "█" * hits + "░" * (len(scored) - hits) if scored else "?"
        print(f"  {key}  {finding:6} {track:10} {bar}  {hits}/{len(scored) or '?'}")

    print("-" * 72)
    print("RECALL по трекам (доля попаданий, усреднённая по вопросам трека):")
    for track, rates in sorted(track_hits.items()):
        avg = sum(rates) / len(rates)
        verdict = "PASS" if avg >= 0.8 else "НЕ ПРОЙДЕН"
        print(f"  {track:12} {avg*100:5.0f}%   {verdict}")

    print("\nPrecision не автоматизируется — оцени вручную по WARNINGS и "
          "по meta «факты ✓/✗» (drop-rate) в детальном выводе прогона 1.")
    print(f"Сырые ответы: {OUT_DIR}/<key>.run<N>.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
