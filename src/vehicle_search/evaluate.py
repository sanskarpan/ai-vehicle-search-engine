from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from .api import create_app
from .seed import seed_database


def _canonical_predicate(predicate: list[Any] | dict[str, Any]) -> tuple[str, str, tuple[Any, ...]]:
    if isinstance(predicate, dict):
        field, operator, values = predicate["field"], predicate["op"], predicate["values"]
    else:
        field, operator, values = predicate
    normalized = (
        tuple(sorted(values, key=str))
        if operator in {"in", "not_in", "contains_all"}
        else tuple(values)
    )
    return field, operator, normalized


def _matches(vehicle: dict[str, Any], predicate: dict[str, Any]) -> bool:
    field = predicate["field"]
    value = {
        "adult_safety_stars": vehicle["safety"]["adult_stars"],
        "child_safety_stars": vehicle["safety"]["child_stars"],
    }.get(field, vehicle.get(field))
    expected = predicate["values"]
    operator = predicate["op"]
    if operator == "contains_all":
        return set(expected) <= set(value)
    if operator == "in":
        return value in expected
    if operator == "not_in":
        return value not in expected
    if value is None:
        return False
    target = expected[0]
    return {
        "eq": value == target,
        "lt": value < target,
        "lte": value <= target,
        "gt": value > target,
        "gte": value >= target,
    }[operator]


def _revision() -> str | None:
    try:
        return subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def run(path: str, dataset: str) -> dict[str, Any]:
    dataset_path = Path(dataset)
    rows = [json.loads(line) for line in dataset_path.read_text().splitlines() if line.strip()]
    client = TestClient(create_app(path))
    requested_mode = os.getenv("PARSER_MODE", "offline").strip().lower()
    case_results = []
    status_correct = canonical_exact = result_set_exact = clarification_correct = 0
    canonical_count = result_set_count = clarification_count = 0
    returned_rows = hard_violations = 0
    live_extractions = degraded_responses = 0

    for row in rows:
        response = client.post("/api/v1/search", json={"query": row["query"], "limit": 50})
        body = response.json()
        status_ok = response.status_code == 200 and body.get("status") == row["expected_status"]
        checks = {"status": status_ok}
        meta = body.get("meta") if isinstance(body, dict) else None
        meta = meta if isinstance(meta, dict) else {}
        is_live_extraction = meta.get("parser_mode") == "llm" and meta.get("degraded") is False
        live_extractions += is_live_extraction
        degraded_responses += meta.get("degraded") is True
        if requested_mode == "llm":
            checks["live_execution"] = is_live_extraction
        if row["expected_status"] == "needs_clarification":
            clarification_count += 1
            clarification_ok = (
                status_ok and body.get("results") == [] and body.get("clarification") is not None
            )
            clarification_correct += clarification_ok
            checks["clarification"] = clarification_ok
        else:
            expected_predicates = row.get("expected_predicates")
            if expected_predicates is not None:
                canonical_count += 1
                actual_interpretation = body.get("interpretation") or {}
                actual_predicates = sorted(
                    _canonical_predicate(item)
                    for item in actual_interpretation.get("predicates", [])
                )
                labelled_predicates = sorted(
                    _canonical_predicate(item) for item in expected_predicates
                )
                actual_preferences = sorted(
                    item["code"] for item in actual_interpretation.get("preferences", [])
                )
                expected_preferences = sorted(row.get("expected_preferences", []))
                expected_sort = row.get("expected_sort", "relevance")
                canonical_ok = (
                    status_ok
                    and actual_predicates == labelled_predicates
                    and actual_preferences == expected_preferences
                    and actual_interpretation.get("sort") == expected_sort
                )
                canonical_exact += canonical_ok
                checks["canonical"] = canonical_ok
            if "expected_ids" in row:
                result_set_count += 1
                actual_ids = [item["vehicle"]["id"] for item in body.get("results", [])]
                result_ok = status_ok and set(actual_ids) == set(row["expected_ids"])
                if "expected_order" in row:
                    result_ok = result_ok and actual_ids == row["expected_order"]
                if "expected_first" in row:
                    result_ok = (
                        result_ok and bool(actual_ids) and actual_ids[0] == row["expected_first"]
                    )
                result_set_exact += result_ok
                checks["results"] = result_ok
            for item in body.get("results", []):
                returned_rows += 1
                predicates = (body.get("interpretation") or {}).get("predicates", [])
                if not all(_matches(item["vehicle"], predicate) for predicate in predicates):
                    hard_violations += 1
        status_correct += status_ok
        case_results.append({"id": row["id"], "ok": all(checks.values()), "checks": checks})

    passed = sum(result["ok"] for result in case_results)
    prompt_path = Path(__file__).with_name("parsing") / "prompt.txt"
    return {
        "dataset": str(dataset_path),
        "dataset_sha256": hashlib.sha256(dataset_path.read_bytes()).hexdigest(),
        "git_revision": _revision(),
        "parser_mode": requested_mode,
        "provider": os.getenv("LLM_PROVIDER") if requested_mode == "llm" else None,
        "model": os.getenv("LLM_MODEL") if requested_mode == "llm" else None,
        "live_extractions": live_extractions,
        "degraded_responses": degraded_responses,
        "prompt_sha256": hashlib.sha256(prompt_path.read_bytes()).hexdigest(),
        "count": len(rows),
        "passed": passed,
        "status_accuracy": status_correct / len(rows) if rows else None,
        "canonical_exact_match": canonical_exact / canonical_count if canonical_count else None,
        "result_set_exact_match": result_set_exact / result_set_count if result_set_count else None,
        "clarification_accuracy": clarification_correct / clarification_count
        if clarification_count
        else None,
        "hard_constraint_violations": hard_violations,
        "returned_rows_checked": returned_rows,
        "cases": case_results,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--db", help="Existing seeded database; defaults to a temporary 8-row anchor catalogue"
    )
    parser.add_argument("--dataset", default="data/golden_queries.jsonl")
    args = parser.parse_args()
    if args.db:
        report = run(args.db, args.dataset)
    else:
        with tempfile.TemporaryDirectory(prefix="vehicle-eval-") as directory:
            database = str(Path(directory) / "anchors.db")
            seed_database(database, count=8, seed=42)
            report = run(database, args.dataset)
    print(json.dumps(report, indent=2))
    if report["passed"] != report["count"] or report["hard_constraint_violations"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
