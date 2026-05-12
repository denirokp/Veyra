"""Запуск eval-set против работающего API.

Использование:
    python scripts/run_eval.py [--url http://localhost:8000] [--yaml tests/eval_set.yaml]

Выводит:
    - Результат каждого кейса: PASS / FAIL / ERROR
    - Итоговую сводку: N/15 прошло, среднее время
    - Сохраняет JSON-отчёт в tests/eval_results_<timestamp>.json
"""
import argparse
import asyncio
import json
import sys
import time
from datetime import datetime
from pathlib import Path

import httpx
import yaml


def load_cases(yaml_path: str) -> list[dict]:
    with open(yaml_path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data.get("cases", [])


async def run_case(client: httpx.AsyncClient, base_url: str, case: dict) -> dict:
    query = case["query"]
    t0 = time.monotonic()
    try:
        resp = await client.post(
            f"{base_url}/api/chat",
            json={"message": query},
            timeout=60.0,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        return {
            "id": case["id"],
            "status": "ERROR",
            "error": str(e),
            "latency_ms": int((time.monotonic() - t0) * 1000),
        }

    latency_ms = int((time.monotonic() - t0) * 1000)

    answer = data.get("answer", "")
    facts = data.get("facts", [])
    mode_detected = data.get("metadata", {}).get("mode_detected", "")

    failures = []

    # Mode check
    expected_mode = case.get("expected_mode")
    if expected_mode and mode_detected != expected_mode:
        failures.append(f"mode={mode_detected!r} expected={expected_mode!r}")

    # Required keywords
    for kw in case.get("required_keywords", []):
        if kw.lower() not in answer.lower():
            failures.append(f"missing keyword: {kw!r}")

    # Forbidden keywords (hallucination guard)
    for kw in case.get("forbidden_keywords", []):
        if kw.lower() in answer.lower():
            failures.append(f"forbidden keyword found: {kw!r}")

    # Min facts
    min_facts = case.get("min_facts", 0)
    if len(facts) < min_facts:
        failures.append(f"facts={len(facts)} < min_facts={min_facts}")

    # Sources validation
    if case.get("require_sources") and facts:
        missing_source = [
            f["statement"][:40]
            for f in facts
            if not f.get("source") or not f["source"].get("title")
        ]
        if missing_source:
            failures.append(f"facts missing source: {missing_source[:2]}")

    status = "PASS" if not failures else "FAIL"
    return {
        "id": case["id"],
        "status": status,
        "failures": failures,
        "mode_detected": mode_detected,
        "facts_count": len(facts),
        "answer_preview": answer[:120],
        "latency_ms": latency_ms,
    }


async def main(base_url: str, yaml_path: str) -> int:
    cases = load_cases(yaml_path)
    if not cases:
        print("No cases found in eval set.")
        return 1

    print(f"Running {len(cases)} eval cases against {base_url}\n")
    results = []

    async with httpx.AsyncClient() as client:
        # Check health first
        try:
            r = await client.get(f"{base_url}/health", timeout=5.0)
            r.raise_for_status()
        except Exception as e:
            print(f"ERROR: API not reachable at {base_url}: {e}")
            return 1

        for case in cases:
            print(f"  [{case['id']}] {case['query'][:60]!r} ... ", end="", flush=True)
            result = await run_case(client, base_url, case)
            results.append(result)
            if result["status"] == "PASS":
                print(f"PASS ({result['latency_ms']}ms)")
            elif result["status"] == "ERROR":
                print(f"ERROR: {result.get('error', '')}")
            else:
                print(f"FAIL: {result['failures']}")

    passed = sum(1 for r in results if r["status"] == "PASS")
    errors = sum(1 for r in results if r["status"] == "ERROR")
    failed = len(results) - passed - errors
    avg_latency = sum(r.get("latency_ms", 0) for r in results) / len(results)

    print(f"\n{'='*60}")
    print(f"Result: {passed}/{len(results)} passed, {failed} failed, {errors} errors")
    print(f"Avg latency: {avg_latency:.0f}ms")

    # Save JSON report
    report = {
        "timestamp": datetime.utcnow().isoformat(),
        "base_url": base_url,
        "total": len(results),
        "passed": passed,
        "failed": failed,
        "errors": errors,
        "avg_latency_ms": round(avg_latency),
        "cases": results,
    }
    out_path = Path("tests") / f"eval_results_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"
    out_path.parent.mkdir(exist_ok=True)
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Report saved: {out_path}")

    return 0 if failed == 0 and errors == 0 else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run Хроника eval set")
    parser.add_argument("--url", default="http://localhost:8000", help="API base URL")
    parser.add_argument("--yaml", default="tests/eval_set.yaml", help="Eval set YAML path")
    args = parser.parse_args()

    sys.exit(asyncio.run(main(args.url, args.yaml)))
