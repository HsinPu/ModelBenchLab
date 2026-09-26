from sqlalchemy import select

from app.db import Item, Review, Run, Session
from app.execution import execute_item


CASE = {
    "title": "算術",
    "messages": [{"role": "user", "content": "2 + 2 = ?"}],
    "rule": {"kind": "exact", "expected": "4"},
}


def create_demo_run(client):
    model_id = client.post("/api/models", json={
        "name": "Demo", "provider": "demo", "model": "demo-stable", "api_key": "test",
    }).json()["id"]
    dataset_id = client.post("/api/datasets", json={"name": "題庫", "cases": [CASE]}).json()["id"]
    prompt_id = client.post("/api/prompts", json={"name": "v1", "text": ""}).json()["id"]
    response = client.post("/api/runs", json={
        "name": "測試", "dataset_id": dataset_id, "prompt_id": prompt_id, "model_ids": [model_id],
    })
    assert response.status_code == 201, response.text
    return response.json()["id"]


def test_archived_run_disappears_but_keeps_snapshot_items_and_review(client):
    run_id = create_demo_run(client)
    with Session() as db:
        item_id = db.scalar(select(Item.id).where(Item.run_id == run_id))
    execute_item(item_id)
    assert client.post(f"/api/items/{item_id}/review", json={"score": 5, "note": "保留"}).status_code == 201

    deleted = client.delete(f"/api/runs/{run_id}")
    assert deleted.status_code == 200
    assert deleted.json() == {"deleted": True, "runs": 1}
    assert not any(run["id"] == run_id for run in client.get("/api/runs").json())
    assert client.get(f"/api/runs/{run_id}").status_code == 404
    assert client.get(f"/api/runs/{run_id}/export").status_code == 404
    assert client.get(f"/api/runs/{run_id}/events").status_code == 404
    assert client.post(f"/api/runs/{run_id}/retry").status_code == 404
    assert client.post(f"/api/items/{item_id}/review", json={"score": 4, "note": "無法新增"}).status_code == 404
    assert client.post(f"/api/items/{item_id}/evaluate").status_code == 404
    with Session() as db:
        archived = db.get(Run, run_id)
        assert archived.deleted_at is not None
        assert archived.snapshot["cases"][0]["title"] == "算術"
        assert db.get(Item, item_id).result is not None
        assert db.scalar(select(Review.note).where(Review.item_id == item_id)) == "保留"
    assert client.delete(f"/api/runs/{run_id}").status_code == 200
    assert client.delete("/api/runs/missing").status_code == 404


def test_active_run_requires_cancellation_before_deletion(client):
    run_id = create_demo_run(client)
    assert client.delete(f"/api/runs/{run_id}").status_code == 409
    assert client.post(f"/api/runs/{run_id}/cancel").status_code == 200
    assert client.get(f"/api/runs/{run_id}").json()["status"] == "cancelled"
    assert client.delete(f"/api/runs/{run_id}").status_code == 200


def test_deleting_one_batch_record_archives_whole_batch(client):
    snapshot = {"models": [], "dataset_name": "整批", "cases": []}
    with Session() as db:
        db.add_all([
            Run(id="batch-a", name="整批 1/2", status="completed", snapshot=snapshot, batch_id="batch"),
            Run(id="batch-b", name="整批 2/2", status="completed", snapshot=snapshot, batch_id="batch"),
        ])
        db.flush()
        db.add(Item(id="pending", run_id="batch-b", model_id="demo", case_index=0, repeat_index=0, status="queued"))
        db.commit()
    assert client.delete("/api/runs/batch-a").status_code == 409
    with Session() as db:
        db.get(Item, "pending").status = "completed"
        db.commit()
    deleted = client.delete("/api/runs/batch-a")
    assert deleted.status_code == 200
    assert deleted.json()["runs"] == 2
    assert client.get("/api/runs").json() == []
    with Session() as db:
        rows = db.scalars(select(Run).where(Run.batch_id == "batch")).all()
        assert len({row.deleted_at for row in rows}) == 1
        assert all(row.deleted_at is not None for row in rows)
