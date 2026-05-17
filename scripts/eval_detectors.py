"""Eval-харнес детекторов (G1) — precision-review находок «бульона».

Гейт `run_gate.py` мерит recall полнотекстового анализа Claude. Этот харнес
мерит ДРУГОЕ — precision самих детекторов: какая доля уже найденных
расхождений / логических сигналов / обещаний реально верна.

Как работает: фетчит находки через API запущенного бэкенда, для каждой
берёт текст документов-источников и прогоняет находку через LLM-judge —
«подтверждается ли это источником». Считает precision = confirmed /
(confirmed + rejected).

Запуск (сервер на localhost:8000, LLM_API_KEY задан в backend/.env):
    python scripts/eval_detectors.py                 # все типы, все находки
    python scripts/eval_detectors.py --limit 15      # выборка по 15 на тип
    python scripts/eval_detectors.py numeric logic   # только эти типы
    python scripts/eval_detectors.py --model <name>  # модель судьи

Оговорки (G1, см. docs/GAP-ANALYSIS-AVITO.md):
  • LLM-judge — НЕ человеческая разметка. Это автоматический фильтр явных
    ошибок, а не итоговый ground truth. Финальная валидация требует
    независимой разметки аналитиком.
  • Для настоящей независимости модель судьи (--model) должна отличаться
    от модели, которой работали детекторы — иначе проверка частично
    циклична.
  • Фрагменты документов обрезаются — судья может вернуть «unclear», если
    значения не попали в окно.

Только stdlib.
"""
from __future__ import annotations

import json
import random
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

BASE = "http://localhost:8000"
OUT_DIR = Path(__file__).parent.parent / "gate-out"
ENV_PATH = Path(__file__).parent.parent / "backend" / ".env"
TYPES = ("numeric", "logic", "promises")

JUDGE_SYSTEM = (
    "Ты — независимый проверяющий (LLM-judge). Тебе дают НАХОДКУ детектора "
    "и фрагменты документов-источников. Реши, верна ли находка.\n"
    "ФОРМАТ ОТВЕТА: ровно один JSON-объект, без markdown и без рассуждений "
    "вне его. Первый символ ответа — `{`. Всё объяснение помести внутрь "
    "поля reason, 1–2 предложения.\n"
    '{"verdict": "confirmed"|"rejected"|"unclear", "reason": "<кратко>"}\n'
    "confirmed — находка фактически подтверждается источниками.\n"
    "rejected — находка неверна: искажение цитаты, не тот смысл, выдумка, "
    "ложное противоречие (разные периоды/сегменты, «план vs факт»).\n"
    "unclear — фрагментов недостаточно для решения.\n"
    "Будь строгим: при сомнении выбирай rejected или unclear, не confirmed."
)


# ── infra ─────────────────────────────────────────────────────────────────────

def _load_env() -> dict:
    """Читает backend/.env (KEY=VALUE). Переменные окружения имеют приоритет."""
    import os
    env: dict[str, str] = {}
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            env[k.strip()] = v.strip().strip('"').strip("'")
    for k in ("LLM_API_KEY", "LLM_BASE_URL", "LLM_MODEL", "API_AUTH_TOKEN"):
        if os.environ.get(k):
            env[k] = os.environ[k]
    return env


def _api_headers(env: dict) -> dict:
    h = {"Content-Type": "application/json"}
    if env.get("API_AUTH_TOKEN"):
        h["Authorization"] = f"Bearer {env['API_AUTH_TOKEN']}"
    return h


def _get(path: str, headers: dict, timeout: int = 60):
    req = urllib.request.Request(BASE + path, headers=headers, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _check_server(headers: dict) -> bool:
    try:
        _get("/health", headers, timeout=5)
        return True
    except urllib.error.URLError as exc:
        print(f"❌ Сервер на {BASE} недоступен: {exc.reason}")
        print("   Подними бэкенд:  cd ~/Veyra/backend && uvicorn app.main:app")
        return False
    except Exception as exc:  # noqa: BLE001
        print(f"❌ /health не ответил: {exc}")
        return False


def _llm_judge(user: str, *, model: str, api_key: str, base_url: str) -> str:
    """LLM-вызов судьи через OpenAI-совместимый API. Ретраи с backoff."""
    url = base_url.rstrip("/") + "/chat/completions"
    body = json.dumps({
        "model": model,
        "temperature": 0,
        "max_tokens": 1024,
        "messages": [
            {"role": "system", "content": JUDGE_SYSTEM},
            {"role": "user", "content": user},
        ],
    }).encode("utf-8")
    headers = {"Content-Type": "application/json",
               "Authorization": f"Bearer {api_key}"}
    last: Exception | None = None
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, data=body, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=120) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            return data["choices"][0]["message"]["content"] or ""
        except Exception as exc:  # noqa: BLE001
            last = exc
            if attempt < 2:
                time.sleep(2 ** attempt + random.random())
    assert last is not None
    raise last


def _parse_verdict(raw: str) -> tuple[str, str]:
    text = (raw or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"\n?```\s*$", "", text).strip()
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            d = json.loads(match.group())
            v = str(d.get("verdict", "")).lower().strip()
            if v not in ("confirmed", "rejected", "unclear"):
                v = "unclear"
            return v, str(d.get("reason", "")).strip()
        except json.JSONDecodeError:
            pass
    return "unclear", "судья вернул неразборный ответ: " + text[:200]


def _excerpt(text: str, needles: list[str], window: int = 700, cap: int = 7000) -> str:
    """Релевантный фрагмент: окна вокруг вхождений needles. Если ничего не
    найдено — обрезка с начала."""
    text = text or ""
    if not text:
        return "(текст документа недоступен)"
    low = text.lower()
    spans: list[tuple[int, int]] = []
    for n in needles:
        key = (n or "").strip().lower()[:60]
        if len(key) < 3:
            continue
        start = 0
        while len(spans) <= 12:
            idx = low.find(key, start)
            if idx == -1:
                break
            spans.append((max(0, idx - window), min(len(text), idx + len(key) + window)))
            start = idx + len(key)
    if not spans:
        return text[:cap] + (" …[обрезано]" if len(text) > cap else "")
    spans.sort()
    merged = [spans[0]]
    for s, e in spans[1:]:
        if s <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], e))
        else:
            merged.append((s, e))
    out = "\n …\n".join(text[s:e] for s, e in merged)
    return out[:cap] + (" …[обрезано]" if len(out) > cap else "")


# ── doc text cache ─────────────────────────────────────────────────────────────

_doc_cache: dict[str, str] = {}


def _doc_text(doc_id: str | None, headers: dict) -> str:
    if not doc_id:
        return ""
    if doc_id not in _doc_cache:
        try:
            data = _get(f"/api/documents/{doc_id}/text", headers)
            _doc_cache[doc_id] = data.get("text") or ""
        except Exception:  # noqa: BLE001 — удалён/недоступен
            _doc_cache[doc_id] = ""
    return _doc_cache[doc_id]


# ── prompt builders ─────────────────────────────────────────────────────────────

def _prompt_numeric(c: dict, headers: dict) -> str:
    metric = str(c.get("metric", "?"))
    va, vb = str(c.get("value_a", "?")), str(c.get("value_b", "?"))
    ta = c.get("document_a", {}).get("title", "?")
    tb = c.get("document_b", {}).get("title", "?")
    ex_a = _excerpt(_doc_text(c.get("document_a", {}).get("id"), headers), [metric, va])
    ex_b = _excerpt(_doc_text(c.get("document_b", {}).get("id"), headers), [metric, vb])
    return (
        f"НАХОДКА — числовое расхождение.\n"
        f"Метрика: {metric}\nПериод: {c.get('period') or '—'}\n"
        f"Документ A «{ta}»: значение {va}\n"
        f"Документ B «{tb}»: значение {vb}\n\n"
        f"ФРАГМЕНТ ДОКУМЕНТА A:\n{ex_a}\n\n"
        f"ФРАГМЕНТ ДОКУМЕНТА B:\n{ex_b}\n\n"
        f"Проверь: (1) значение {va} действительно относится к метрике "
        f"«{metric}» в документе A, а {vb} — в документе B; (2) это одна и "
        f"та же метрика и сопоставимые величины; (3) расхождение реально, "
        f"а не объясняется разными периодами/сегментами/«план vs факт». "
        f"Верни JSON."
    )


def _prompt_logic(s: dict, headers: dict) -> str:
    sa, sb = str(s.get("statement_a", "?")), str(s.get("statement_b", "?"))
    ta = s.get("document_a", {}).get("title", "?")
    tb = s.get("document_b", {}).get("title", "?")
    ex_a = _excerpt(_doc_text(s.get("document_a", {}).get("id"), headers), [sa[:40]])
    ex_b = _excerpt(_doc_text(s.get("document_b", {}).get("id"), headers), [sb[:40]])
    return (
        f"НАХОДКА — логический сигнал, тип «{s.get('signal_type', '?')}».\n"
        f"Документ A «{ta}», утверждение: {sa}\n"
        f"Документ B «{tb}», утверждение: {sb}\n\n"
        f"ФРАГМЕНТ ДОКУМЕНТА A:\n{ex_a}\n\n"
        f"ФРАГМЕНТ ДОКУМЕНТА B:\n{ex_b}\n\n"
        f"Проверь: (1) оба утверждения действительно присутствуют в своих "
        f"документах (не искажены); (2) между ними действительно есть "
        f"логическая связь заявленного типа, а не натянутая. Верни JSON."
    )


def _prompt_promise(p: dict, headers: dict) -> str:
    text = str(p.get("text", "?"))
    title = p.get("document", {}).get("title", "?")
    ex = _excerpt(_doc_text(p.get("document", {}).get("id"), headers),
                  [text[:50], str(p.get("metric") or ""), str(p.get("target_value") or "")])
    return (
        f"НАХОДКА — обещание (обязательство) из документа «{title}».\n"
        f"Текст: {text}\n"
        f"Метрика: {p.get('metric') or '—'}  целевое: {p.get('target_value') or '—'}  "
        f"дедлайн: {p.get('deadline') or '—'}\n\n"
        f"ФРАГМЕНТ ДОКУМЕНТА:\n{ex}\n\n"
        f"Проверь: это действительно обещание/обязательство/план, реально "
        f"присутствующее в документе — а не общая фраза, вопрос, "
        f"констатация факта или выдумка детектора. Верни JSON."
    )


def _claim(kind: str, item: dict) -> str:
    """Однострочное описание находки для отчёта."""
    if kind == "numeric":
        return (f"{item.get('metric', '?')}: {item.get('value_a', '?')} "
                f"vs {item.get('value_b', '?')}")
    if kind == "logic":
        return f"[{item.get('signal_type', '?')}] {str(item.get('statement_a', ''))[:80]}"
    return str(item.get("text", ""))[:100]


# ── main ────────────────────────────────────────────────────────────────────────

SOURCES = {
    "numeric": ("/api/contradictions/numeric", _prompt_numeric, "числовые расхождения"),
    "logic": ("/api/contradictions/logic", _prompt_logic, "логические сигналы"),
    "promises": ("/api/promises", _prompt_promise, "обещания"),
}


def main() -> int:
    # --- аргументы ---
    limit = 0
    model_override = ""
    kinds: list[str] = []
    argv = sys.argv[1:]
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--limit" and i + 1 < len(argv):
            limit = max(0, int(argv[i + 1]))
            i += 2
        elif a == "--model" and i + 1 < len(argv):
            model_override = argv[i + 1]
            i += 2
        elif a in TYPES:
            kinds.append(a)
            i += 1
        else:
            print(f"Неизвестный аргумент: {a}. Типы: {', '.join(TYPES)}")
            return 1
    kinds = kinds or list(TYPES)

    # --- LLM-доступ ---
    env = _load_env()
    api_key = env.get("LLM_API_KEY", "")
    if not api_key:
        print("❌ LLM-judge требует LLM_API_KEY.")
        print(f"   Задай его в {ENV_PATH} или переменной окружения.")
        print("   Без LLM-судьи харнес не запускается (G1, docs/GAP-ANALYSIS-AVITO.md).")
        return 2
    base_url = env.get("LLM_BASE_URL") or "https://api.moonshot.ai/v1"
    model = model_override or env.get("LLM_MODEL") or "moonshot-v1-128k"
    headers = _api_headers(env)

    if not _check_server(headers):
        return 1

    # --- сбор находок ---
    batches: list[tuple[str, list, callable]] = []
    total = 0
    for kind in kinds:
        path, builder, label = SOURCES[kind]
        try:
            items = _get(path + "?status=open", headers)
        except Exception as exc:  # noqa: BLE001
            print(f"❌ Не удалось получить {label}: {exc}")
            return 1
        if limit:
            items = items[:limit]
        batches.append((kind, items, builder))
        total += len(items)
        print(f"  {label}: {len(items)} находок к проверке")

    if total == 0:
        print("\nНечего проверять — находок нет. Корпус проиндексирован? "
              "Детекторы включены (ENABLE_BACKGROUND_SIGNALS)?")
        return 0

    print(f"\nСудья: {model} @ {base_url}")
    print(f"Всего {total} находок → {total} LLM-вызовов судьи. Поехали.\n")

    # --- прогон ---
    records: list[dict] = []
    for kind, items, builder in batches:
        for n, item in enumerate(items, 1):
            try:
                raw = _llm_judge(builder(item, headers),
                                 model=model, api_key=api_key, base_url=base_url)
                verdict, reason = _parse_verdict(raw)
            except Exception as exc:  # noqa: BLE001
                verdict, reason = "error", str(exc)
            records.append({
                "id": item.get("id"),
                "type": kind,
                "claim": _claim(kind, item),
                "verdict": verdict,
                "reason": reason,
            })
            mark = {"confirmed": "✓", "rejected": "✗",
                    "unclear": "?", "error": "!"}.get(verdict, "?")
            print(f"  [{kind:8}] {n:3}/{len(items)}  {mark} {verdict:9} "
                  f"{_claim(kind, item)[:70]}")

    # --- скоркард ---
    print("\n" + "=" * 72)
    print("СКОРКАРД — precision детекторов (по оценке LLM-судьи)")
    print("=" * 72)
    scorecard: dict[str, dict] = {}
    for kind in kinds:
        rs = [r for r in records if r["type"] == kind]
        conf = sum(1 for r in rs if r["verdict"] == "confirmed")
        rej = sum(1 for r in rs if r["verdict"] == "rejected")
        unc = sum(1 for r in rs if r["verdict"] == "unclear")
        err = sum(1 for r in rs if r["verdict"] == "error")
        denom = conf + rej
        prec = (conf / denom) if denom else None
        scorecard[kind] = {"checked": len(rs), "confirmed": conf, "rejected": rej,
                           "unclear": unc, "error": err,
                           "precision": round(prec, 3) if prec is not None else None}
        prec_s = f"{prec*100:5.0f}%" if prec is not None else "  n/a"
        print(f"  {SOURCES[kind][2]:22} проверено {len(rs):3}  "
              f"✓{conf:3} ✗{rej:3} ?{unc:3} !{err:2}   precision {prec_s}")
    print("-" * 72)
    print("precision = confirmed / (confirmed + rejected); unclear/error не в знаменателе.")

    # --- отчёты ---
    OUT_DIR.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d-%H%M")
    payload = {"generated_at": datetime.now().isoformat(timespec="seconds"),
               "judge_model": model, "scorecard": scorecard, "records": records}
    json_path = OUT_DIR / f"eval_detectors.{ts}.json"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                         encoding="utf-8")

    md = [f"# Eval детекторов — precision-review\n",
          f"Дата: {payload['generated_at']}  ·  судья: `{model}`  ·  сервер: {BASE}\n",
          "## Скоркард\n",
          "| Тип | Проверено | ✓ confirmed | ✗ rejected | ? unclear | ! error | precision |",
          "|---|---|---|---|---|---|---|"]
    for kind in kinds:
        s = scorecard[kind]
        prec = f"{s['precision']*100:.0f}%" if s["precision"] is not None else "n/a"
        md.append(f"| {SOURCES[kind][2]} | {s['checked']} | {s['confirmed']} | "
                  f"{s['rejected']} | {s['unclear']} | {s['error']} | {prec} |")
    rejected = [r for r in records if r["verdict"] == "rejected"]
    unclear = [r for r in records if r["verdict"] in ("unclear", "error")]
    md.append(f"\n## Отклонённые находки — {len(rejected)} (на ручную проверку)\n")
    for r in rejected:
        md.append(f"- `{r['id']}` [{r['type']}] {r['claim']}\n  - судья: {r['reason']}")
    md.append(f"\n## Неоднозначные / ошибки — {len(unclear)}\n")
    for r in unclear:
        md.append(f"- `{r['id']}` [{r['type']}] {r['claim']}\n  - {r['verdict']}: {r['reason']}")
    md.append(
        "\n## Оговорки\n"
        "- LLM-judge — автоматический фильтр явных ошибок, НЕ итоговый "
        "ground truth. Финальная валидация требует независимой разметки "
        "аналитиком.\n"
        "- Для независимости модель судьи должна отличаться от модели "
        "детекторов (`--model`).\n"
        "- Фрагменты документов обрезаны — часть «unclear» возможна из-за "
        "того, что значение не попало в окно.")
    md_path = OUT_DIR / f"eval_detectors.{ts}.md"
    md_path.write_text("\n".join(md), encoding="utf-8")

    print(f"\nОтчёты:\n  {md_path}\n  {json_path}")
    print("Отклонённые находки — в .md, раздел «Отклонённые находки».")
    return 0


if __name__ == "__main__":
    sys.exit(main())
