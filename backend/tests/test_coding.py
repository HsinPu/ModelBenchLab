import hashlib
import os
import threading
import time

import pytest
from sqlalchemy import select

from app import coding_benchmarks
from app.coding import evaluate_code, program_from_output, runtime
from app.db import Session, Item, Run
from app.execution import execute_item, recover_stale

PROMPT = 'def add(a, b):\n    """Add two numbers."""\n'
TESTS = "def check(candidate):\n    assert candidate(2, 3) == 5\n    assert candidate(-1, 1) == 0\n"


def spec():
    return dict(
        benchmark="humaneval",
        task_id="HumanEval/0",
        entry_point="add",
        prompt=PROMPT,
        tests=TESTS,
        tests_sha256=hashlib.sha256(TESTS.encode()).hexdigest(),
        dataset_repo="openai/openai_humaneval",
        dataset_revision="a" * 40,
        suite_version="hf-tests-v1",
    )


def create(client, monkeypatch, **settings):
    monkeypatch.setattr(
        "app.coding.runtime",
        lambda: {"image_id": "sha256:" + "a" * 64, "runner_version": "hf-tests-v1"},
    )
    model = client.post(
        "/api/models",
        json={"name": "coding mock", "provider": "demo", "model": "demo-stable"},
    ).json()["id"]
    dataset = client.post(
        "/api/datasets",
        json={
            "name": "code",
            "cases": [
                {
                    "title": "add",
                    "messages": [{"role": "user", "content": PROMPT}],
                    "rule": {"kind": "code", "coding": spec()},
                }
            ],
        },
    ).json()["id"]
    prompt = client.post("/api/prompts", json={"name": "code", "text": ""}).json()["id"]
    response = client.post(
        "/api/runs",
        json={
            "name": "code",
            "dataset_id": dataset,
            "model_ids": [model],
            "prompt_id": prompt,
            **settings,
        },
    )
    if response.status_code == 201:
        # Simulated provider metadata, never a real key or HTTP request.
        with Session() as db:
            run = db.get(Run, response.json()["id"])
            snapshot = {
                **run.snapshot,
                "models": [{**run.snapshot["models"][0], "provider": "openrouter"}],
            }
            run.snapshot = snapshot
            db.commit()
        monkeypatch.setattr("app.execution.execution_key", lambda *args: ("", 1))
    return response


def test_code_contract_and_deterministic_preview(client, monkeypatch):
    rows = [
        dict(
            task_id=f"HumanEval/{i}",
            entry_point="add",
            prompt=PROMPT,
            test=TESTS,
            canonical_solution="secret answer",
        )
        for i in range(8)
    ]
    monkeypatch.setattr(coding_benchmarks, "load_rows", lambda *args: rows)
    body = {"benchmark": "humaneval", "revision": "a" * 40, "limit": 3, "seed": 123}
    preview = client.post("/api/benchmarks/coding/preview", json=body).json()
    assert preview == client.post("/api/benchmarks/coding/preview", json=body).json()
    assert len(preview["cases"]) == 3
    assert all(
        "secret answer" not in str(case) and "assert" not in str(case["messages"])
        for case in preview["cases"]
    )
    assert (
        client.post(
            "/api/datasets", json={"name": preview["name"], "cases": preview["cases"]}
        ).status_code
        == 201
    )
    preview["cases"][0]["rule"]["coding"]["tests"] += "# changed"
    assert (
        client.post(
            "/api/datasets", json={"name": "bad", "cases": preview["cases"]}
        ).status_code
        == 422
    )
    body["revision"] = "main"
    assert client.post("/api/benchmarks/coding/preview", json=body).status_code == 422


def test_extract_code():
    assert "return a + b" in program_from_output(
        "```python\ndef add(a,b):\n    return a + b\n```", PROMPT, "add"
    )
    assert "return a + b" in program_from_output("    return a + b\n", PROMPT, "add")
    program_from_output(
        "from __future__ import annotations\ndef add(a,b):\n    return a+b",
        PROMPT,
        "add",
    )
    with pytest.raises(ValueError):
        program_from_output("```python\nx=1\n```\n```python\nx=2\n```", PROMPT, "add")


def test_durable_generation_and_reevaluation_no_provider_call(client, monkeypatch):
    response = create(client, monkeypatch, code_timeout=7)
    assert response.status_code == 201
    rid = response.json()["id"]
    calls = []

    def generate(*args):
        calls.append(1)
        return {
            "output": "def add(a,b):\n    return a+b",
            "latency_ms": 20,
            "input_tokens": 3,
            "output_tokens": 8,
            "demo": False,
            "cost": "0.003",
        }

    monkeypatch.setattr("app.execution.generate", generate)

    def judge(output, rule, settings, cancelled):
        with Session() as db:
            saved = db.scalar(select(Item).where(Item.run_id == rid))
            assert saved.result["cost"] == "0.003"
            assert saved.result["evaluation"]["pending"]
        assert settings["code_timeout"] == 7
        return {"kind": "code", "passed": False, "reason": "wrong", "error": False}

    monkeypatch.setattr("app.execution.evaluate", judge)
    with Session() as db:
        iid = db.scalar(select(Item.id).where(Item.run_id == rid))
    execute_item(iid)
    data = client.get("/api/runs/" + rid).json()
    assert "tests" not in data["snapshot"]["cases"][0]["rule"]["coding"]
    assert (
        client.get("/api/runs/" + rid + "/export").json()["snapshot"]["cases"][0][
            "rule"
        ]["coding"]["tests"]
        == TESTS
    )
    assert data["counts"] == {"completed": 1} and data["pass_rate"] == 0
    assert client.post("/api/items/" + iid + "/evaluate").status_code == 200
    execute_item(iid)
    execute_item(iid)
    assert len(calls) == 1
    assert (
        client.get("/api/runs/" + rid).json()["cost_summary"]["reported_usd"] == "0.003"
    )


def test_coding_force_cancel_late_grade_not_saved(client, monkeypatch):
    rid = create(client, monkeypatch).json()["id"]
    monkeypatch.setattr(
        "app.execution.generate",
        lambda *args: {
            "output": "def add(a,b):\n    return a+b",
            "cost": "0.01",
            "latency_ms": 1,
            "demo": False,
        },
    )

    def judge(*args):
        assert client.post("/api/runs/" + rid + "/force-cancel").status_code == 200
        return {"passed": True, "reason": "late"}

    monkeypatch.setattr("app.execution.evaluate", judge)
    with Session() as db:
        iid = db.scalar(select(Item.id).where(Item.run_id == rid))
    execute_item(iid)
    data = client.get("/api/runs/" + rid).json()
    assert data["status"] == "cancelled" and data["items"][0]["status"] == "cancelled"
    assert data["items"][0]["result"]["evaluation"]["passed"] is None
    assert data["cost_summary"]["reported_usd"] == "0.01"


def test_stale_evaluation_preserves_generated_cost(client, monkeypatch):
    rid = create(client, monkeypatch).json()["id"]
    with Session() as db:
        item = db.scalar(select(Item).where(Item.run_id == rid))
        item.status = "running"
        item.started_at = "2000-01-01T00:00:00+00:00"
        item.result = {
            "output": "saved",
            "cost": "0.01",
            "latency_ms": 1,
            "evaluation": {"passed": None, "pending": True},
        }
        db.get(Run, rid).status = "running"
        db.commit()
    recover_stale()
    data = client.get("/api/runs/" + rid).json()
    assert data["counts"] == {"completed": 1} and data["graded"] == 0
    assert data["items"][0]["result"]["evaluation"]["error"]
    assert data["cost_summary"]["reported_usd"] == "0.01"


def test_runner_required_and_no_multisampling(client, monkeypatch):
    assert create(client, monkeypatch, repeats=2).status_code == 422


def test_coding_ranking_requires_same_runtime_and_timeout(client):
    from app.db import Dataset

    model = {"id": "coding-rank", "name": "code", "provider": "demo"}
    cases = [{"title": "test", "rule": {"kind": "code"}}]
    with Session() as db:
        db.add(Dataset(id="code-bank", name="HumanEval", cases=cases))
        for rid, image, timeout, passed in [
            ("reference", "image-a", 10, True),
            ("other-image", "image-b", 10, False),
            ("other-timeout", "image-a", 20, False),
            ("ungraded", "image-a", 10, None),
        ]:
            # The same model's newer incompatible runs must not replace reference.
            models = (
                [model] if rid != "ungraded" else [{**model, "id": "ungraded-model"}]
            )
            db.add(
                Run(
                    id=rid,
                    name=rid,
                    status="completed",
                    created_at="2026-10-05T00:00:0" + str(len(rid) % 10),
                    snapshot={
                        "dataset_id": "code-bank",
                        "dataset_name": "HumanEval",
                        "cases": cases,
                        "models": models,
                        "settings": {
                            "repeats": 1,
                            "code_timeout": timeout,
                            "coding_runtime": {"image_id": image},
                        },
                    },
                )
            )
            db.flush()
            db.add(
                Item(
                    id=rid + "-item",
                    run_id=rid,
                    model_id=models[0]["id"],
                    case_index=0,
                    repeat_index=0,
                    status="completed",
                    result={"evaluation": {"passed": passed}},
                )
            )
        db.commit()
    ranking = client.get("/api/runs/reference/dataset-ranking").json()
    assert len(ranking["models"]) == 2
    assert (
        ranking["models"][0]["metric"] == "pass@1"
        and ranking["models"][0]["pass_rate"] == 100
    )
    assert ranking["models"][1]["ranked"] is False


@pytest.mark.skipif(
    os.getenv("TEST_CODING_DOCKER") != "1", reason="opt-in real Linux Docker tests"
)
@pytest.mark.parametrize(
    "body,outcome",
    [
        ("return a+b", "passed"),
        ("return 0", "wrong_answer"),
        ('raise RuntimeError("test")', "runtime_error"),
        ("while True: pass", "time_limit"),
        ("import os\n    os._exit(0)", "runtime_error"),
        (
            'import os\n    assert os.getuid() != 0\n    assert not os.path.exists("/var/run/docker.sock")\n    assert not os.path.exists("/app/.env")\n    return a+b',
            "passed",
        ),
        ('open("/runner/probe", "w")\n    return a+b', "runtime_error"),
        (
            'import socket\n    socket.create_connection(("1.1.1.1", 443), timeout=0.5)\n    return a+b',
            "runtime_error",
        ),
    ],
)
def test_real_docker_outcomes(body, outcome):
    result = evaluate_code(
        "def add(a,b):\n    " + body,
        spec(),
        {"coding_runtime": runtime(), "code_timeout": 1},
    )
    assert result["outcome"] == outcome, result


@pytest.mark.skipif(
    os.getenv("TEST_CODING_DOCKER") != "1", reason="opt-in real Linux Docker tests"
)
def test_real_docker_cancel():
    cancelled = threading.Event()
    timer = threading.Timer(1, cancelled.set)
    timer.start()
    started = time.monotonic()
    result = evaluate_code(
        "def add(a,b):\n    while True: pass",
        spec(),
        {"coding_runtime": runtime(), "code_timeout": 30},
        cancelled.is_set,
    )
    timer.cancel()
    assert result["outcome"] == "cancelled"
    assert time.monotonic() - started < 15


@pytest.mark.skipif(
    os.getenv("TEST_CODING_DOCKER") != "1", reason="opt-in real Linux Docker tests"
)
def test_real_docker_memory_limit():
    result = evaluate_code(
        "def add(a,b):\n    data=bytearray(1024*1024*1024)\n    return a+b",
        spec(),
        {"coding_runtime": runtime(), "code_timeout": 10},
    )
    assert result["passed"] is False and result["error"] is False, result


@pytest.mark.skipif(
    os.getenv("TEST_CODING_DOCKER") != "1", reason="opt-in real Linux Docker tests"
)
def test_real_worker_docker_without_paid_requests(client, monkeypatch):
    environment = runtime()
    response = create(client, monkeypatch)
    rid = response.json()["id"]
    with Session() as db:
        run = db.get(Run, rid)
        run.snapshot = {
            **run.snapshot,
            "settings": {**run.snapshot["settings"], "coding_runtime": environment},
        }
        iid = db.scalar(select(Item.id).where(Item.run_id == rid))
        db.commit()
    calls = []

    def mock_generate(*args):
        calls.append(1)
        return {
            "output": "def add(a,b):\n    return a+b",
            "cost": "0.01",
            "latency_ms": 1,
            "input_tokens": 1,
            "output_tokens": 1,
            "demo": True,
        }

    monkeypatch.setattr("app.execution.generate", mock_generate)
    execute_item(iid)
    data = client.get("/api/runs/" + rid).json()
    assert data["status"] == "completed" and data["graded"] == data["passed"] == 1
    assert data["items"][0]["result"]["evaluation"]["runtime"] == environment
    assert client.post("/api/items/" + iid + "/evaluate").status_code == 200
    execute_item(iid)
    assert len(calls) == 1
    assert (
        client.get("/api/runs/" + rid + "/dataset-ranking").json()["models"][0][
            "metric"
        ]
        == "pass@1"
    )
