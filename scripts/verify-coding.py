"""Opt-in live dataset/reference validation. No model API or user database access."""

import argparse
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.coding import evaluate_code, runtime
from app.coding_benchmarks import BENCHMARKS, load_rows

parser = argparse.ArgumentParser()
parser.add_argument("--questions", type=int, default=10)
args = parser.parse_args()
environment = runtime()
for benchmark, source in BENCHMARKS.items():
    rows = load_rows(benchmark, source["revision"])
    count = min(args.questions, len(rows))
    outcomes = []
    for row in rows[:count]:
        spec = {
            "prompt": row["prompt"],
            "entry_point": row["entry_point"],
            "tests": row["test"],
            "tests_sha256": hashlib.sha256(row["test"].encode()).hexdigest(),
        }
        result = evaluate_code(
            row["prompt"] + row["canonical_solution"],
            spec,
            {"coding_runtime": environment, "code_timeout": 10},
        )
        outcomes.append({"task_id": row["task_id"], "outcome": result["outcome"]})
    print(
        json.dumps(
            {
                "benchmark": benchmark,
                "revision": source["revision"],
                "available": len(rows),
                "validated": count,
                "passed": sum(r["outcome"] == "passed" for r in outcomes),
                "outcomes": outcomes,
                "runtime": environment,
            }
        ),
        flush=True,
    )
    if any(result["outcome"] != "passed" for result in outcomes):
        raise SystemExit(1)
