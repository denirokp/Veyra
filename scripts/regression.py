"""Регрессионный харнес (G4) — валидация на каждое изменение поведения.

`run_gate.py` и `eval_detectors.py` — разовые прогоны. Этот харнес делает
их регрессией: запоминает baseline и при изменении поведенческих файлов
(SKILL.md, промпты детекторов, ground truth) прогоняет проверки и
сравнивает с baseline — упала метрика или нет.

Запуск:
    python scripts/regression.py                    # прогон + сравнение с baseline
    python scripts/regression.py --update-baseline  # записать текущий прогон как baseline
    python scripts/regression.py --check-changed     # exit 0 если поведенческие файлы менялись

Коды возврата (обычный режим):
    0 — регрессий нет
    1 — регрессия обнаружена (метрика упала ниже baseline − допуск)
    2 — не удалось прогнать (нет сервера / LLM / baseline)

Код возврата --check-changed:
    0 — поведенческие файлы изменены, регрессию нужно прогнать
    1 — изменений нет

Автозапуск на каждое изменение — через git-хук: см. scripts/hooks/pre-push.

Покрытие: recall (`run_gate.py`, путь /api/chat) и precision детекторов
(`eval_detectors.py`, выборка). Регрессия живого пути SKILL.md (Claude +
ai-lab-mcp) требует Claude-управляемого харнеса и здесь НЕ автоматизирована
— известный предел, см. docs/GAP-ANALYSIS-AVITO.md §3 G4.

Только stdlib.
"""
from __future__ import annotations

import glob
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).parent.parent
SCRIPTS = ROOT / "scripts"
OUT_DIR = ROOT / "gate-out"
BASELINE = OUT_DIR / "baseline.json"

# Поведенческие файлы: их изменение может сдвинуть метрики.
WATCHED = [
    "ai-lab/skills/SKILL.md",
    "backend/app/skills/extract_entities.py",
    "backend/app/skills/track_promises.py",
    "backend/app/skills/find_logic_signals.py",
    "backend/app/skills/find_contradictions.py",
    "backend/app/skills/find_intra_contradictions.py",
    "backend/app/skills/document_brief.py",
    "scripts/gate_ground_truth.json",
]

TOLERANCE = 0.05    # падение метрики больше этого — регрессия
EVAL_SAMPLE = 10    # находок на тип в регрессионном прогоне eval_detectors


def _git(*args: str) -> str | None:
    try:
        out = subprocess.run(["git", *args], cwd=ROOT, capture_output=True,
                             text=True, timeout=15)
        return out.stdout.strip() if out.returncode == 0 else None
    except Exception:  # noqa: BLE001
        return None


def _load_baseline() -> dict | None:
    if not BASELINE.exists():
        return None
    try:
        return json.loads(BASELINE.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None


def _changed_watched(baseline: dict | None) -> list[str]:
    """Поведенческие файлы, изменённые с момента baseline. Если baseline нет
    — считаем, что прогнать нужно (возвращаем весь список)."""
    if baseline is None:
        return list(WATCHED)
    changed: set[str] = set()
    status = _git("status", "--porcelain")
    if status:
        for line in status.splitlines():
            changed.add(line[3:].strip())
    base_commit = baseline.get("git_commit")
    if base_commit:
        diff = _git("diff", "--name-only", base_commit, "HEAD")
        if diff:
            changed.update(diff.splitlines())
    return [w for w in WATCHED if w in changed]


def _run_script(name: str, *args: str) -> int:
    print(f"\n>>> {name} {' '.join(args)}".rstrip())
    proc = subprocess.run([sys.executable, str(SCRIPTS / name), *args])
    return proc.returncode


def _collect() -> tuple[dict, list[str]]:
    """Прогоняет проверки, возвращает (метрики, список пропущенного)."""
    metrics: dict = {}
    skipped: list[str] = []

    # recall — run_gate.py (полный набор кейсов)
    if _run_script("run_gate.py") == 0 and (OUT_DIR / "gate_summary.json").exists():
        data = json.loads((OUT_DIR / "gate_summary.json").read_text(encoding="utf-8"))
        metrics["recall_by_track"] = data.get("recall_by_track", {})
    else:
        skipped.append("recall — run_gate.py не отдал результат (бэкенд поднят?)")

    # precision — eval_detectors.py на ограниченной выборке
    if _run_script("eval_detectors.py", "--limit", str(EVAL_SAMPLE)) == 0:
        files = sorted(glob.glob(str(OUT_DIR / "eval_detectors.*.json")),
                       key=lambda p: Path(p).stat().st_mtime)
        if files:
            data = json.loads(Path(files[-1]).read_text(encoding="utf-8"))
            metrics["precision_by_type"] = {
                k: v.get("precision")
                for k, v in (data.get("scorecard") or {}).items()
            }
        else:
            skipped.append("precision — eval_detectors.py не оставил отчёта")
    else:
        skipped.append("precision — eval_detectors.py не отработал (сервер / LLM_API_KEY?)")

    return metrics, skipped


def _compare(cur: dict, base: dict) -> list[str]:
    """Список регрессий: метрика упала ниже baseline − TOLERANCE."""
    regs: list[str] = []
    for track, val in (cur.get("recall_by_track") or {}).items():
        b = (base.get("recall_by_track") or {}).get(track)
        if b is not None and val is not None and val < b - TOLERANCE:
            regs.append(f"recall[{track}]: {b*100:.0f}% → {val*100:.0f}%")
    for t, val in (cur.get("precision_by_type") or {}).items():
        b = (base.get("precision_by_type") or {}).get(t)
        if b is not None and val is not None and val < b - TOLERANCE:
            regs.append(f"precision[{t}]: {b*100:.0f}% → {val*100:.0f}%")
    return regs


def main() -> int:
    args = sys.argv[1:]
    baseline = _load_baseline()

    # --- режим проверки изменений (для git-хука) ---
    if "--check-changed" in args:
        changed = _changed_watched(baseline)
        if changed:
            print("Изменены поведенческие файлы:")
            for c in changed:
                print(f"  • {c}")
            print("→ регрессию нужно прогнать.")
            return 0
        print("Поведенческие файлы не менялись — регрессию можно пропустить.")
        return 1

    OUT_DIR.mkdir(exist_ok=True)
    update = "--update-baseline" in args

    metrics, skipped = _collect()
    if not metrics:
        print("\n❌ Не удалось собрать ни одной метрики. "
              "Подними бэкенд (uvicorn app.main:app) и задай LLM_API_KEY.")
        return 2

    # --- обновление baseline ---
    if update:
        record = {
            "committed_at": datetime.now().isoformat(timespec="seconds"),
            "git_commit": _git("rev-parse", "HEAD"),
            **metrics,
        }
        BASELINE.write_text(json.dumps(record, ensure_ascii=False, indent=2),
                            encoding="utf-8")
        print(f"\n✅ Baseline обновлён: {BASELINE}")
        for s in skipped:
            print(f"   ⚠ пропущено: {s}")
        return 0

    # --- сравнение с baseline ---
    print("\n" + "=" * 72)
    print("РЕГРЕССИЯ — сравнение с baseline")
    print("=" * 72)
    if baseline is None:
        print("Baseline не найден. Зафиксируй текущий прогон как эталон:")
        print("  python scripts/regression.py --update-baseline")
        return 2

    for s in skipped:
        print(f"  ⚠ пропущено: {s}")

    regs = _compare(metrics, baseline)
    if regs:
        print(f"\n❌ РЕГРЕССИЯ ({len(regs)}):")
        for r in regs:
            print(f"  ↓ {r}")
        print(f"\nBaseline от {baseline.get('committed_at', '?')} "
              f"(commit {str(baseline.get('git_commit'))[:8]}).")
        print("Если падение ожидаемо — обнови baseline:")
        print("  python scripts/regression.py --update-baseline")
        return 1

    print(f"\n✅ Регрессий нет — метрики не ниже baseline "
          f"(допуск {TOLERANCE*100:.0f} п.п.).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
