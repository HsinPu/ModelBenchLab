from sqlalchemy import select

from app.db import Dataset, Item, Session
from app.execution import execute_item


CASE = {
    "title": "算術",
    "messages": [{"role": "user", "content": "2 + 2 = ?"}],
    "rule": {"kind": "exact", "expected": "4"},
}


def test_delete_dataset_hides_it_but_preserves_existing_run(client):
    dataset_id = client.post("/api/datasets", json={"name": "待刪除題庫", "cases": [CASE]}).json()["id"]
    model_id = client.post("/api/models", json={
        "name": "Demo", "provider": "demo", "model": "demo-stable", "api_key": "test",
    }).json()["id"]
    prompt_id = client.post("/api/prompts", json={"name": "v1", "text": ""}).json()["id"]
    run = client.post("/api/runs", json={
        "name": "歷史測試", "dataset_id": dataset_id,
        "prompt_id": prompt_id, "model_ids": [model_id],
    })
    assert run.status_code == 201, run.text
    run_id = run.json()["id"]

    deleted = client.delete(f"/api/datasets/{dataset_id}")
    assert deleted.status_code == 200
    assert deleted.json() == {"deleted": True, "batches": 1}
    assert all(d["id"] != dataset_id for d in client.get("/api/datasets").json())
    with Session() as db:
        row = db.get(Dataset, dataset_id)
        assert row.deleted_at is not None
        assert row.cases[0]["title"] == "算術"
        item_id = db.scalar(select(Item.id).where(Item.run_id == run_id))

    execute_item(item_id)
    historical = client.get(f"/api/runs/{run_id}")
    assert historical.status_code == 200
    assert historical.json()["snapshot"]["cases"][0]["title"] == "算術"
    assert historical.json()["status"] == "completed"
    assert client.post("/api/runs", json={
        "name": "不能再用", "dataset_id": dataset_id,
        "prompt_id": prompt_id, "model_ids": [model_id],
    }).status_code == 404
    assert client.delete(f"/api/datasets/{dataset_id}").status_code == 200
    assert client.delete("/api/datasets/missing").status_code == 404


def test_delete_bundle_archives_every_part(client):
    cases = [{**CASE, "title": f"題目 {index}"} for index in range(1001)]
    created = client.post("/api/datasets/batch", json={"name": "整組題庫", "cases": cases})
    assert created.status_code == 201, created.text
    bundle_id = created.json()["bundle_id"]
    parts = [row for row in client.get("/api/datasets").json() if row["bundle_id"] == bundle_id]
    assert len(parts) == 2

    deleted = client.delete(f"/api/datasets/{parts[0]['id']}")
    assert deleted.status_code == 200
    assert deleted.json()["batches"] == 2
    assert not any(row["bundle_id"] == bundle_id for row in client.get("/api/datasets").json())
    with Session() as db:
        stored = db.scalars(select(Dataset).where(Dataset.bundle_id == bundle_id)).all()
        assert len(stored) == 2
        assert len({row.deleted_at for row in stored}) == 1
        assert all(row.deleted_at is not None for row in stored)
    assert client.post("/api/run-batches", json={
        "name": "不可新建", "bundle_id": bundle_id,
        "model_ids": ["missing"], "prompt_id": "missing",
    }).status_code == 404
