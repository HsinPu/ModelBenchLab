from app.db import Item, Run, Session


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
