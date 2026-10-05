from sqlalchemy import select

from app.costs import reported_cost
from app.db import Item, Run, Session


def test_reported_cost_accepts_only_valid_openrouter_charges():
    assert reported_cost({"cost": "0.00000001"}, "openrouter") is not None
    assert reported_cost({"cost": "0"}, "openrouter") is not None
    for value in (None, -1, "NaN", "Infinity", True, "bad"):
        assert reported_cost({"cost": value}, "openrouter") is None
    assert reported_cost({"cost": "0.1"}, "demo") is None
    assert reported_cost({"cost": "0.1", "cost_source": "catalog_estimate"}, "openrouter") is None


def test_run_cost_updates_after_each_reported_answer(client):
    models = [
        {"id": "openrouter-model", "name": "OpenRouter", "provider": "openrouter"},
        {"id": "custom-model", "name": "Custom", "provider": "openai-compatible"},
        {"id": "demo-model", "name": "Demo", "provider": "demo"},
    ]
    with Session() as db:
        db.add(Run(
            id="cost-run", name="cost check", status="running",
            snapshot={"models": models, "dataset_name": "test", "cases": []},
        ))
        db.flush()
        db.add_all([
            Item(id="a", run_id="cost-run", model_id="openrouter-model", case_index=0,
                 repeat_index=0, status="completed", result={"cost": "0.00000001", "cost_source": "openrouter_usage", "latency_ms": 1}),
            Item(id="b", run_id="cost-run", model_id="openrouter-model", case_index=1,
                 repeat_index=0, status="completed", result={"cost": "0.00000002", "latency_ms": 1}),
            Item(id="c", run_id="cost-run", model_id="openrouter-model", case_index=2,
                 repeat_index=0, status="completed", result={"cost": None, "latency_ms": 1}),
            Item(id="d", run_id="cost-run", model_id="openrouter-model", case_index=3,
                 repeat_index=0, status="failed"),
            Item(id="e", run_id="cost-run", model_id="openrouter-model", case_index=4,
                 repeat_index=0, status="queued"),
            Item(id="f", run_id="cost-run", model_id="custom-model", case_index=5,
                 repeat_index=0, status="completed", result={"cost": None, "latency_ms": 1}),
            Item(id="g", run_id="cost-run", model_id="demo-model", case_index=6,
                 repeat_index=0, status="completed", result={"demo": True, "latency_ms": 1}),
            Item(id="h", run_id="cost-run", model_id="openrouter-model", case_index=7,
                 repeat_index=0, status="failed", attempts=[{"status": "failed", "diagnostics": {"reported_cost_usd": "0.00000005"}}]),
            Item(id="i", run_id="cost-run", model_id="openrouter-model", case_index=8,
                 repeat_index=0, status="completed", result={"cost": "0.00000006", "latency_ms": 1},
                 attempts=[{"status": "failed", "diagnostics": {"reported_cost_usd": "0.00000007"}}]),
        ])
        db.commit()

    summary = client.get("/api/runs").json()[0]["cost_summary"]
    assert summary["reported_usd"] == "0.00000021"
    assert summary["reported_items"] == 4
    assert summary["unknown_items"] == 3
    assert summary["by_model"]["openrouter-model"]["unknown_items"] == 2
    assert summary["by_model"]["custom-model"]["unknown_items"] == 1
    assert "demo-model" not in summary["by_model"]

    with Session() as db:
        item = db.scalar(select(Item).where(Item.id == "e"))
        item.status = "completed"
        item.result = {"cost": "0.00000004", "cost_source": "openrouter_usage", "latency_ms": 1}
        db.commit()
    updated = client.get("/api/runs").json()[0]["cost_summary"]
    assert updated["reported_usd"] == "0.00000025"
    assert updated["reported_items"] == 5
    assert updated["unknown_items"] == 3
