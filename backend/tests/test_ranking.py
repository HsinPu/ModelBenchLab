from app.db import Dataset, Item, Run, Session

MODELS = [
    {"id": "a", "name": "Alpha", "provider": "openai-compatible"},
    {"id": "b", "name": "Auto Router", "provider": "openrouter", "catalog": {"fixed_model": False}},
    {"id": "c", "name": "Manual", "provider": "openai-compatible"},
]


def result(passed):
    return {"evaluation": {"passed": passed}}


def test_ranking_compares_only_same_run_batch_and_excludes_ungraded(client):
    snapshot = {"models": MODELS, "dataset_name": "同一題庫"}
    with Session() as db:
        db.add_all([
            Run(id="part-one", name="測試 1/2", status="completed", batch_id="batch", snapshot=snapshot),
            Run(id="part-two", name="測試 2/2", status="running", batch_id="batch", snapshot=snapshot),
            Run(id="other", name="其他測試", status="completed", snapshot=snapshot),
        ])
        db.flush()
        db.add_all([
            Item(id="a1", run_id="part-one", model_id="a", case_index=0, repeat_index=0, status="completed", result=result(True)),
            Item(id="a2", run_id="part-one", model_id="a", case_index=1, repeat_index=0, status="completed", result=result(False)),
            Item(id="a3", run_id="part-two", model_id="a", case_index=2, repeat_index=0, status="completed", result=result(True)),
            Item(id="a4", run_id="part-two", model_id="a", case_index=3, repeat_index=0, status="queued"),
            Item(id="b1", run_id="part-one", model_id="b", case_index=0, repeat_index=0, status="completed", result=result(False)),
            Item(id="b2", run_id="part-two", model_id="b", case_index=2, repeat_index=0, status="failed"),
            Item(id="c1", run_id="part-one", model_id="c", case_index=0, repeat_index=0, status="completed", result=result(None)),
            Item(id="c2", run_id="part-two", model_id="c", case_index=2, repeat_index=0, status="cancelled"),
            Item(id="other-a", run_id="other", model_id="a", case_index=0, repeat_index=0, status="completed", result=result(False)),
        ])
        db.commit()

    response = client.get("/api/runs/part-two/ranking")
    assert response.status_code == 200
    ranking = response.json()
    assert ranking["run_count"] == 2
    assert ranking["is_final"] is False
    assert ranking["status"] == "running"
    assert [model["model_id"] for model in ranking["models"]] == ["a", "b", "c"]
    assert ranking["models"][0] == {
        "model_id": "a", "name": "Alpha", "provider": "openai-compatible", "dynamic_model": False,
        "total": 4, "completed": 3, "failed": 0, "cancelled": 0,
        "graded": 3, "passed": 2, "pass_rate": 66.7,
    }
    assert ranking["models"][1]["pass_rate"] == 0.0
    assert ranking["models"][1]["dynamic_model"] is True
    assert ranking["models"][1]["failed"] == 1
    assert ranking["models"][2]["pass_rate"] is None
    assert ranking["models"][2]["graded"] == 0
    assert ranking["models"][2]["cancelled"] == 1
    assert client.get("/api/runs/other/ranking").json()["models"][0]["pass_rate"] == 0.0

    with Session() as db:
        db.get(Item, "a4").status = "completed"
        db.get(Item, "a4").result = result(False)
        db.get(Run, "part-two").status = "completed_with_errors"
        db.commit()
    final = client.get("/api/runs/part-one/ranking").json()
    assert final["is_final"] is True
    assert final["status"] == "completed_with_errors"
    assert final["models"][0]["pass_rate"] == 50.0
    with Session() as db:
        db.get(Run, "part-two").status = "cancelled"
        db.commit()
    assert client.get("/api/runs/part-one/ranking").json()["status"] == "cancelled"
    with Session() as db:
        db.get(Run, "part-one").deleted_at = "2026-09-25"
        db.commit()
    assert client.get("/api/runs/part-one/ranking").status_code == 404


def test_ranking_missing_run(client):
    assert client.get("/api/runs/missing/ranking").status_code == 404


def test_dataset_ranking_compares_runs_without_promoting_partial_results(client):
    cases = [{"input": f"question {number}"} for number in range(3)]
    qwen = {"id": "qwen", "name": "Qwen", "provider": "openrouter"}
    glm = {"id": "glm", "name": "GLM", "provider": "openrouter"}
    with Session() as db:
        db.add_all([
            Dataset(id="bank", name="TMMLU+", cases=cases),
            Dataset(id="other-bank", name="TMMLU+", cases=cases),
        ])
        db.add_all([
            Run(id="qwen-old", name="Qwen old", status="completed", created_at="2026-09-24T00:00:00", snapshot={"dataset_id": "bank", "dataset_name": "TMMLU+", "cases": cases, "models": [qwen]}),
            Run(id="qwen", name="Qwen", status="completed_with_errors", created_at="2026-09-25T00:00:00", snapshot={"dataset_id": "bank", "dataset_name": "TMMLU+", "cases": cases, "models": [qwen]}),
            Run(id="glm", name="GLM", status="running", created_at="2026-09-26T00:00:00", snapshot={"dataset_id": "bank", "dataset_name": "TMMLU+", "cases": cases, "models": [glm]}),
            Run(id="glm-retry", name="GLM retry", status="completed", created_at="2026-09-27T00:00:00", snapshot={"dataset_id": "bank", "dataset_name": "TMMLU+", "cases": cases, "models": [glm], "retry_of": "glm"}),
            Run(id="other", name="Other", status="completed", created_at="2026-09-26T00:00:00", snapshot={"dataset_id": "other-bank", "dataset_name": "TMMLU+", "cases": cases, "models": [{"id": "other", "name": "Other", "provider": "demo"}]}),
        ])
        db.flush()
        db.add_all([
            Item(id="old", run_id="qwen-old", model_id="qwen", case_index=0, repeat_index=0, status="completed", result=result(True)),
            Item(id="q1", run_id="qwen", model_id="qwen", case_index=0, repeat_index=0, status="completed", result=result(True)),
            Item(id="q2", run_id="qwen", model_id="qwen", case_index=1, repeat_index=0, status="completed", result=result(False)),
            Item(id="q3", run_id="qwen", model_id="qwen", case_index=2, repeat_index=0, status="failed"),
            Item(id="g1", run_id="glm", model_id="glm", case_index=0, repeat_index=0, status="completed", result=result(True)),
            Item(id="g2", run_id="glm", model_id="glm", case_index=1, repeat_index=0, status="queued"),
            Item(id="g3", run_id="glm", model_id="glm", case_index=2, repeat_index=0, status="queued"),
            Item(id="gr", run_id="glm-retry", model_id="glm", case_index=1, repeat_index=0, status="completed", result=result(True)),
            Item(id="other-item", run_id="other", model_id="other", case_index=0, repeat_index=0, status="completed", result=result(True)),
        ])
        db.commit()

    response = client.get("/api/runs/glm-retry/dataset-ranking")
    assert response.status_code == 200
    ranking = response.json()
    assert ranking["dataset_name"] == "TMMLU+"
    assert ranking["question_count"] == 3
    assert ranking["is_final"] is False
    assert [model["model_id"] for model in ranking["models"]] == ["qwen", "glm"]
    assert ranking["models"][0]["pass_rate"] == 50.0
    assert ranking["models"][0]["total"] == 3
    assert ranking["models"][0]["failed"] == 1
    assert ranking["models"][0]["ranked"] is True
    assert ranking["models"][1]["pass_rate"] == 100.0
    assert ranking["models"][1]["graded"] == 1
    assert ranking["models"][1]["ranked"] is False
    assert ranking["models"][1]["provisional"] is True

    with Session() as db:
        db.get(Run, "qwen").deleted_at = "2026-09-27"
        db.commit()
    assert client.get("/api/runs/qwen/dataset-ranking").status_code == 404
    remaining = client.get("/api/runs/glm/dataset-ranking").json()["models"]
    assert {model["model_id"] for model in remaining} == {"qwen", "glm"}
    assert all(model["ranked"] is False for model in remaining)
    assert client.get("/api/runs/other/dataset-ranking").json()["models"][0]["model_id"] == "other"


def test_dataset_ranking_merges_complete_batches_only(client):
    alpha = {"id": "a", "name": "Alpha", "provider": "demo"}
    beta = {"id": "b", "name": "Beta", "provider": "demo"}
    snapshots = {
        "first": {"dataset_id": "first", "dataset_name": "Bank 1/2", "cases": [{"input": "one"}]},
        "second": {"dataset_id": "second", "dataset_name": "Bank 2/2", "cases": [{"input": "two"}]},
    }
    with Session() as db:
        db.add_all([
            Dataset(id="first", name="Bank 1/2", cases=snapshots["first"]["cases"], bundle_id="bundle", bundle_name="Bank", bundle_index=1, bundle_total=2),
            Dataset(id="second", name="Bank 2/2", cases=snapshots["second"]["cases"], bundle_id="bundle", bundle_name="Bank", bundle_index=2, bundle_total=2),
        ])
        for model, batch, stamp in ((alpha, "batch-a", "2026-09-25"), (beta, "batch-b", "2026-09-26")):
            for dataset_id in ("first", "second"):
                db.add(Run(id=f"{batch}-{dataset_id}", name=batch, status="completed", batch_id=batch, created_at=stamp, snapshot={**snapshots[dataset_id], "models": [model]}))
        db.add(Run(id="partial", name="partial", status="completed", created_at="2026-09-27", snapshot={**snapshots["first"], "models": [{"id": "partial", "name": "Partial", "provider": "demo"}]}))
        db.flush()
        for batch, model_id, passed in (("batch-a", "a", True), ("batch-b", "b", False)):
            for dataset_id in ("first", "second"):
                db.add(Item(id=f"{batch}-{dataset_id}-item", run_id=f"{batch}-{dataset_id}", model_id=model_id, case_index=0, repeat_index=0, status="completed", result=result(passed)))
        db.add(Item(id="partial-item", run_id="partial", model_id="partial", case_index=0, repeat_index=0, status="completed", result=result(True)))
        db.commit()

    ranking = client.get("/api/runs/batch-b-second/dataset-ranking").json()
    assert ranking["dataset_name"] == "Bank"
    assert ranking["question_count"] == 2
    assert [model["model_id"] for model in ranking["models"]] == ["a", "b"]
    assert [model["total"] for model in ranking["models"]] == [2, 2]
    assert [model["pass_rate"] for model in ranking["models"]] == [100.0, 0.0]
