import json
from concurrent.futures import ThreadPoolExecutor
import httpx
import pytest
from sqlalchemy import select
from app import openrouter
from app.db import Session, Model, ProviderConnection, CatalogModel, Run, Item
from app.security import decrypt
from app.providers import generate, ProviderError
from app.execution import execute_item


def entry(mid="maker/text", **overrides):
    return {
        "id": mid,
        "name": mid,
        "context_length": 32000,
        "architecture": {"input_modalities": ["text"], "output_modalities": ["text"]},
        "supported_parameters": ["temperature", "max_tokens", "tools"],
        "top_provider": {"max_completion_tokens": 65536},
        "pricing": {"prompt": "0", "completion": "0"},
        **overrides,
    }


@pytest.fixture
def upstream(monkeypatch):
    rows = [
        entry(),
        entry("maker/paid", pricing={"prompt": "0.000001", "completion": "0.000003"}),
        entry("openrouter/auto"),
        entry(
            "maker/image",
            architecture={"input_modalities": ["text"], "output_modalities": ["image"]},
        ),
    ]
    calls = []

    def metadata(path, key):
        calls.append((path, key))
        return (
            {"limit": 20, "limit_remaining": 18, "usage": 2, "label": "do-not-store"}
            if path == "/key"
            else rows
        )

    monkeypatch.setattr(openrouter, "get_metadata", metadata)
    return rows, calls


def connect(client, upstream, name="OpenRouter test"):
    response = client.post(
        "/api/connections", json={"name": name, "api_key": "test-key-not-real"}
    )
    assert response.status_code == 201
    cid = response.json()["id"]
    assert client.post(f"/api/connections/{cid}/verify").status_code == 200
    assert client.post(f"/api/connections/{cid}/sync").status_code == 200
    return cid


def imported(client, cid, mid="maker/text"):
    response = client.post(f"/api/connections/{cid}/models", json={"model_ids": [mid]})
    assert response.status_code == 201
    return response.json()["ids"][0]


def test_reasoning_effort_is_editable_and_snapshotted(client, upstream, monkeypatch):
    cid = connect(client, upstream)
    response = client.post(
        f"/api/connections/{cid}/models",
        json={"model_ids": ["maker/text"], "reasoning_effort": "low"},
    )
    assert response.status_code == 201
    mid = response.json()["ids"][0]
    assert client.get("/api/models").json()[0]["reasoning_effort"] == "low"

    captured = []

    def trial(config, messages, settings, key):
        captured.append((config["reasoning_effort"], settings["max_tokens"], key))
        return {"output": "OK", "latency_ms": 1}

    monkeypatch.setattr("app.main.generate", trial)
    assert client.post(f"/api/models/{mid}/test").status_code == 200
    assert captured == [("low", 32768, "test-key-not-real")]

    first = run_with(client, mid)
    assert first.status_code == 201
    first_snapshot = client.get(f"/api/runs/{first.json()['id']}").json()["snapshot"]
    assert first_snapshot["models"][0]["reasoning_effort"] == "low"
    changed = client.patch(f"/api/models/{mid}", json={"reasoning_effort": "ultra"})
    assert changed.status_code == 200
    assert changed.json()["reasoning_effort"] == "ultra"
    second = run_with(client, mid)
    assert second.status_code == 201
    second_snapshot = client.get(f"/api/runs/{second.json()['id']}").json()["snapshot"]
    assert second_snapshot["models"][0]["reasoning_effort"] == "ultra"
    assert client.get(f"/api/runs/{first.json()['id']}").json()["snapshot"] == first_snapshot
    assert client.patch(f"/api/models/{mid}", json={"reasoning_effort": "other"}).status_code == 422
    assert client.patch(f"/api/models/{mid}", json={"reasoning_effort": None}).json()["reasoning_effort"] is None


def test_output_token_limit_defaults_edits_and_run_snapshots(client, upstream, monkeypatch):
    cid = connect(client, upstream)
    mid = imported(client, cid)
    assert client.get("/api/models").json()[0]["max_output_tokens"] == 32768

    captured = []
    monkeypatch.setattr(
        "app.main.generate",
        lambda config, messages, settings, key: (
            captured.append(settings["max_tokens"])
            or {"output": "OK", "latency_ms": 1}
        ),
    )
    assert client.post(f"/api/models/{mid}/test").status_code == 200
    assert captured == [32768]

    first = run_with(client, mid)
    assert first.status_code == 201
    first_id = first.json()["id"]
    original = client.get(f"/api/runs/{first_id}").json()["snapshot"]
    assert original["models"][0]["max_output_tokens"] == 32768
    assert original["settings"]["max_tokens"] is None

    updated = client.patch(f"/api/models/{mid}", json={"max_output_tokens": 4096})
    assert updated.status_code == 200
    assert updated.json()["max_output_tokens"] == 4096
    assert client.post(f"/api/models/{mid}/test").status_code == 200
    assert captured == [32768, 4096]
    second = run_with(client, mid)
    assert second.status_code == 201
    second_snapshot = client.get(f"/api/runs/{second.json()['id']}").json()["snapshot"]
    assert second_snapshot["models"][0]["max_output_tokens"] == 4096
    override = run_with(client, mid, max_tokens=2048)
    assert override.status_code == 201

    observed = []
    monkeypatch.setattr(
        "app.execution.generate",
        lambda config, messages, settings, key: (
            observed.append(settings["max_tokens"])
            or {"output": "ok", "latency_ms": 1}
        ),
    )
    for rid in (first_id, second.json()["id"], override.json()["id"]):
        assert execute_run(client, rid)["counts"] == {"completed": 1}
    assert observed == [32768, 4096, 2048]
    assert client.get(f"/api/runs/{first_id}").json()["snapshot"] == original

    source = run_with(client, mid)
    monkeypatch.setattr(
        "app.execution.generate",
        lambda *args: (_ for _ in ()).throw(ProviderError("temporary failure")),
    )
    assert execute_run(client, source.json()["id"])["counts"] == {"failed": 1}
    assert client.patch(f"/api/models/{mid}", json={"max_output_tokens": 8192}).status_code == 200
    retried = client.post(f"/api/runs/{source.json()['id']}/retry")
    assert retried.status_code == 201
    observed.clear()
    monkeypatch.setattr(
        "app.execution.generate",
        lambda config, messages, settings, key: (
            observed.append(settings["max_tokens"])
            or {"output": "ok", "latency_ms": 1}
        ),
    )
    assert execute_run(client, retried.json()["id"])["counts"] == {"completed": 1}
    assert observed == [4096]
    for value in (0, -1, 131073, None):
        assert client.patch(f"/api/models/{mid}", json={"max_output_tokens": value}).status_code == 422


def test_network_wait_is_configurable_for_trial_and_run(client, upstream, monkeypatch):
    cid = connect(client, upstream)
    mid = imported(client, cid)
    observed = []
    monkeypatch.setattr(
        "app.main.generate",
        lambda config, messages, settings, key: (
            observed.append(settings["timeout"])
            or {"output": "OK", "latency_ms": 1}
        ),
    )
    assert client.post(f"/api/models/{mid}/test").status_code == 200
    assert client.post(f"/api/models/{mid}/test", json={"timeout": 345}).status_code == 200
    assert observed == [600, 345]
    for value in (4, 601, 1.5):
        assert client.post(f"/api/models/{mid}/test", json={"timeout": value}).status_code == 422
    assert observed == [600, 345]

    default = run_with(client, mid)
    assert default.status_code == 201
    assert client.get(f"/api/runs/{default.json()['id']}").json()["snapshot"]["settings"]["timeout"] == 600
    custom = run_with(client, mid, timeout=345)
    assert custom.status_code == 201
    assert client.get(f"/api/runs/{custom.json()['id']}").json()["snapshot"]["settings"]["timeout"] == 345
    for value in (4, 601, 1.5):
        assert run_with(client, mid, timeout=value).status_code == 422

def run_with(client, mid, **settings):
    dataset = client.post(
        "/api/datasets",
        json={
            "name": "test",
            "cases": [
                {"title": "hello", "messages": [{"role": "user", "content": "hi"}]}
            ],
        },
    ).json()["id"]
    prompt = client.post("/api/prompts", json={"name": "test", "text": ""}).json()["id"]
    return client.post(
        "/api/runs",
        json={
            "name": "test",
            "dataset_id": dataset,
            "prompt_id": prompt,
            "model_ids": [mid],
            **settings,
        },
    )


def execute_run(client, rid):
    item = client.get(f"/api/runs/{rid}").json()["items"][0]
    execute_item(item["id"])
    return client.get(f"/api/runs/{rid}").json()


def test_secrets_verify_and_fixed_endpoint(client, upstream):
    cid = connect(client, upstream)
    rows, calls = upstream
    assert calls == [("/key", "test-key-not-real"), ("/models", "test-key-not-real")]
    public = client.get("/api/connections").json()[0]
    assert "test-key" not in str(public) and "do-not-store" not in str(public)
    assert public["usage"]["limit_remaining"] == 18
    assert public["endpoint"] == openrouter.BASE_URL
    with Session() as db:
        assert db.get(ProviderConnection, cid).secret != "test-key-not-real"
        assert decrypt(db.get(ProviderConnection, cid).secret) == "test-key-not-real"
    bad = client.post(
        "/api/connections",
        json={
            "name": "",
            "api_key": "do-not-echo-secret",
            "endpoint": "https://evil.example",
        },
    )
    assert (
        bad.status_code == 422
        and "do-not-echo-secret" not in bad.text
        and "evil.example" not in bad.text
    )
    bad = client.post(
        "/api/models",
        json={
            "name": "x",
            "model": "x",
            "endpoint": "bad",
            "api_key": "do-not-echo-secret",
        },
    )
    assert bad.status_code == 422 and "do-not-echo-secret" not in bad.text


def test_catalog_cache_filter_import_and_retirement(client, upstream):
    cid = connect(client, upstream)
    assert client.post(f"/api/connections/{cid}/sync").json()["cached"] is True
    assert len(upstream[1]) == 2
    catalog = client.get(
        f"/api/connections/{cid}/catalog?free_only=true&q=maker&capability=tools"
    ).json()
    assert catalog["total"] == 1 and catalog["items"][0]["model_id"] == "maker/text"
    assert (
        client.get(f"/api/connections/{cid}/catalog?text_only=false&limit=1").json()[
            "total"
        ]
        == 4
    )
    router = client.post(
        f"/api/connections/{cid}/models", json={"model_ids": ["openrouter/auto"]}
    )
    assert router.status_code == 201
    router_model = next(
        model for model in client.get("/api/models").json()
        if model["model"] == "openrouter/auto"
    )
    assert router_model["available"] is True
    assert router_model["catalog"]["fixed_model"] is False
    assert router_model["routing"] == {}
    assert run_with(client, router_model["id"]).status_code == 201
    assert (
        client.post(
            f"/api/connections/{cid}/models", json={"model_ids": ["maker/image"]}
        ).status_code
        == 422
    )
    mid = imported(client, cid)
    duplicate = client.post(
        f"/api/connections/{cid}/models",
        json={"model_ids": ["maker/text", "maker/text"]},
    ).json()
    assert duplicate["created"] == 0 and duplicate["skipped"] == 1
    original = next(model for model in client.get("/api/models").json() if model["id"] == mid)
    upstream[0][:] = [entry("maker/paid")]
    assert client.post(f"/api/connections/{cid}/sync?force=true").status_code == 200
    current = next(model for model in client.get("/api/models").json() if model["id"] == mid)
    assert current["id"] == mid and not current["available"] and original["available"]
    assert run_with(client, mid).status_code == 409


def test_catalog_add_flow_filters_before_pagination(client, upstream):
    cid = connect(client, upstream)
    imported(client, cid)
    upstream[0].append(
        entry("maker/no-temperature", supported_parameters=["max_tokens"])
    )
    client.post(f"/api/connections/{cid}/sync?force=true")
    page = client.get(
        f"/api/connections/{cid}/catalog?unadded_only=true&selectable_only=true&limit=1"
    ).json()
    assert page["total"] == 3
    assert [item["model_id"] for item in page["items"]] == ["maker/no-temperature"]
    all_items = client.get(f"/api/connections/{cid}/catalog").json()
    assert all_items["total"] == 4
    no_temperature = client.post(
        f"/api/connections/{cid}/models",
        json={"model_ids": ["maker/no-temperature"]},
    )
    assert no_temperature.status_code == 201
    assert run_with(client, no_temperature.json()["ids"][0]).status_code == 201


def test_model_unavailable_reason_distinguishes_model_and_connection(client, upstream):
    cid = connect(client, upstream)
    mid = imported(client, cid)
    client.patch(f"/api/models/{mid}", json={"enabled": False})
    model = next(m for m in client.get("/api/models").json() if m["id"] == mid)
    assert model["unavailable_reason"] == "模型已停用"
    client.patch(f"/api/models/{mid}", json={"enabled": True})
    client.patch(f"/api/connections/{cid}", json={"enabled": False})
    model = next(m for m in client.get("/api/models").json() if m["id"] == mid)
    assert model["unavailable_reason"] == "廠商連線已停用"


def test_delete_model_preserves_history_and_allows_readding(client, upstream):
    cid = connect(client, upstream)
    mid = imported(client, cid)
    run = run_with(client, mid)
    assert run.status_code == 201
    rid = run.json()["id"]
    blocked = client.delete(f"/api/models/{mid}")
    assert blocked.status_code == 409
    assert "排隊或執行中" in blocked.json()["detail"]

    with Session() as db:
        db.get(Run, rid).status = "completed"
        db.scalar(select(Item).where(Item.run_id == rid)).status = "completed"
        db.commit()

    assert client.delete(f"/api/models/{mid}").json() == {"deleted": True}
    assert client.get("/api/models").json() == []
    assert client.get(f"/api/runs/{rid}").json()["items"][0]["model_id"] == mid
    assert client.post(f"/api/models/{mid}/test").status_code == 409
    assert client.patch(f"/api/models/{mid}", json={"enabled": True}).status_code == 404
    assert client.delete(f"/api/models/{mid}").json() == {"deleted": True}

    catalog = client.get(
        f"/api/connections/{cid}/catalog?unadded_only=true&selectable_only=true"
    ).json()
    assert "maker/text" in [item["model_id"] for item in catalog["items"]]
    replacement = imported(client, cid)
    assert replacement != mid
    assert [item["id"] for item in client.get("/api/models").json()] == [replacement]


def test_failed_sync_preserves_cached_rows(client, upstream, monkeypatch):
    cid = connect(client, upstream)
    before = client.get(f"/api/connections/{cid}/catalog").json()

    def failed(_):
        raise ProviderError("safe error", True)

    monkeypatch.setattr(openrouter, "list_models", failed)
    assert client.post(f"/api/connections/{cid}/sync?force=true").status_code == 502
    after = client.get(f"/api/connections/{cid}/catalog").json()
    assert (
        after["items"] == before["items"] and after["synced_at"] == before["synced_at"]
    )
    assert after["error"] == "safe error"


def test_concurrent_import_is_idempotent_and_connections_independent(client, upstream):
    cid = connect(client, upstream)

    def add(_):
        return client.post(
            f"/api/connections/{cid}/models", json={"model_ids": ["maker/text"]}
        )

    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(add, range(2)))
    assert all(r.status_code == 201 for r in results)
    assert sum(r.json()["created"] for r in results) == 1
    cid2 = connect(client, upstream, "second")
    imported(client, cid2)
    assert len(client.get("/api/models").json()) == 2


def test_rotation_invalidates_verification_and_pending_jobs(
    client, upstream, monkeypatch
):
    cid = connect(client, upstream)
    mid = imported(client, cid)
    rid = run_with(client, mid).json()["id"]
    snapshot = client.get(f"/api/runs/{rid}").json()["snapshot"]
    assert "test-key" not in json.dumps(snapshot)
    assert snapshot["models"][0]["routing"] == openrouter.DEFAULT_ROUTING
    assert (
        client.patch(
            f"/api/connections/{cid}", json={"api_key": "new-test-key"}
        ).json()["status"]
        == "unverified"
    )
    monkeypatch.setattr(
        "app.execution.generate",
        lambda *a, **k: pytest.fail("must not generate before verify"),
    )
    result = execute_run(client, rid)
    assert result["counts"] == {"failed": 1} and result["snapshot"] == snapshot
    assert result["items"][0]["attempts"][0]["code"] == "connection_unverified"
    assert client.post(f"/api/runs/{rid}/retry").status_code == 409
    assert client.post(f"/api/connections/{cid}/verify").status_code == 200
    assert client.post(f"/api/runs/{rid}/retry").status_code == 201


def test_disabled_connection_or_model_blocks_calls(client, upstream, monkeypatch):
    cid = connect(client, upstream)
    mid = imported(client, cid)
    rid = run_with(client, mid).json()["id"]
    assert (
        client.patch(f"/api/connections/{cid}", json={"enabled": False}).status_code
        == 200
    )
    monkeypatch.setattr(
        "app.execution.generate",
        lambda *a, **k: pytest.fail("disabled connection made a call"),
    )
    assert execute_run(client, rid)["counts"] == {"failed": 1}
    assert client.post(f"/api/models/{mid}/test").status_code == 409
    client.patch(f"/api/connections/{cid}", json={"enabled": True})
    client.patch(f"/api/models/{mid}", json={"enabled": False})
    assert run_with(client, mid).status_code == 409


def test_validation_and_rotation_during_verify(client, upstream, monkeypatch):
    cid = connect(client, upstream)
    mid = imported(client, cid)
    with Session() as db:
        row = db.scalar(select(CatalogModel).where(CatalogModel.model_id == "maker/text"))
        row.details = {**row.details, "max_completion_tokens": 1024}
        db.commit()
    assert run_with(client, mid).status_code == 422
    assert run_with(client, mid, max_tokens=2048).status_code == 422
    with Session() as db:
        row = db.scalar(
            select(CatalogModel).where(CatalogModel.model_id == "maker/text")
        )
        row.details = {**row.details, "supported_parameters": ["max_tokens"]}
        db.commit()
    assert run_with(client, mid).status_code == 422

    def rotate(_):
        client.patch(
            f"/api/connections/{cid}", json={"api_key": "replacement-test-key"}
        )
        return {"limit": None}

    monkeypatch.setattr(openrouter, "verify_key", rotate)
    assert client.post(f"/api/connections/{cid}/verify").status_code == 409
    assert client.get("/api/connections").json()[0]["status"] == "unverified"


def test_manual_connection_credentials(client):
    model = client.post(
        "/api/models",
        json={
            "name": "local",
            "model": "test",
            "endpoint": "http://localhost:11434/v1",
            "api_key": "manual-test-key",
        },
    ).json()
    assert model["connection_id"] and model["available"]
    with Session() as db:
        assert not db.get(Model, model["id"]).secret
        assert (
            decrypt(db.get(ProviderConnection, model["connection_id"]).secret)
            == "manual-test-key"
        )
    client.patch(
        f"/api/connections/{model['connection_id']}",
        json={"api_key": "rotated-test-key"},
    )
    assert client.get("/api/models").json()[0]["available"]


def test_provider_types_and_shared_manual_connection(client, monkeypatch):
    providers = {p["id"]: p for p in client.get("/api/providers").json()}
    assert providers["openrouter"]["supports_catalog"] is True
    assert providers["openrouter"]["verification"] == "metadata"
    assert providers["openai-compatible"]["supports_catalog"] is False
    assert providers["openai-compatible"]["verification"] == "model_trial"
    assert providers["openai-compatible"]["requires_endpoint"] is True

    created = client.post(
        "/api/connections",
        json={
            "provider": "openai-compatible",
            "name": "Local service",
            "endpoint": "http://localhost:11434/v1/",
        },
    )
    assert created.status_code == 201
    connection = created.json()
    cid = connection["id"]
    assert connection["endpoint"] == "http://localhost:11434/v1"
    assert not connection["has_key"] and connection["status"] == "not_applicable"
    assert client.post(f"/api/connections/{cid}/verify").status_code == 422
    assert client.post(f"/api/connections/{cid}/sync").status_code == 422
    assert client.get(f"/api/connections/{cid}/catalog").status_code == 422

    ids = []
    for model_id in ("local/one", "local/two"):
        result = client.post(
            f"/api/connections/{cid}/models/manual",
            json={
                "name": model_id,
                "model_id": model_id,
                "reasoning_effort": "xhigh" if model_id == "local/one" else None,
            },
        )
        assert result.status_code == 201 and result.json()["created"]
        ids.append(result.json()["id"])
    duplicate = client.post(
        f"/api/connections/{cid}/models/manual",
        json={"name": "again", "model_id": "local/one"},
    ).json()
    assert duplicate == {"created": False, "id": ids[0]}
    rows = [m for m in client.get("/api/models").json() if m["connection_id"] == cid]
    assert {m["id"] for m in rows} == set(ids)
    assert all(m["available"] and not m["has_key"] for m in rows)
    assert {m["model"]: m["reasoning_effort"] for m in rows} == {
        "local/one": "xhigh", "local/two": None
    }
    assert run_with(client, ids[0]).status_code == 201

    updated = client.patch(
        f"/api/connections/{cid}",
        json={"endpoint": "https://gateway.example/v1", "api_key": "new-fake-key"},
    )
    assert (
        updated.status_code == 200
        and updated.json()["endpoint"] == "https://gateway.example/v1"
    )
    assert updated.json()["status"] == "not_applicable"
    assert all(
        m["endpoint"] == "https://gateway.example/v1"
        for m in client.get("/api/models").json()
    )
    with Session() as db:
        assert decrypt(db.get(ProviderConnection, cid).secret) == "new-fake-key"
        assert all(not db.get(Model, mid).secret for mid in ids)
    observed = []

    def fake_generate(config, messages, settings, key):
        observed.append((config["model"], config["endpoint"], key, config["reasoning_effort"]))
        return {"output": "ok", "latency_ms": 1, "demo": False, "output_tokens": 1}

    monkeypatch.setattr("app.execution.generate", fake_generate)
    for mid in ids:
        run_id = run_with(client, mid).json()["id"]
        assert execute_run(client, run_id)["counts"] == {"completed": 1}
    assert observed == [
        ("local/one", "https://gateway.example/v1", "new-fake-key", "xhigh"),
        ("local/two", "https://gateway.example/v1", "new-fake-key", None),
    ]
    assert (
        client.patch(f"/api/connections/{cid}", json={"enabled": False}).status_code
        == 200
    )
    assert run_with(client, ids[1]).status_code == 409
    assert (
        client.post(
            f"/api/connections/{cid}/models/manual",
            json={"name": "third", "model_id": "local/three"},
        ).status_code
        == 409
    )


def test_provider_type_and_endpoint_validation(client):
    for payload in (
        {"provider": "unknown", "name": "x", "api_key": "not-real"},
        {
            "provider": "openrouter",
            "name": "x",
            "api_key": "not-real",
            "endpoint": "https://evil.example/v1",
        },
        {
            "provider": "openai-compatible",
            "name": "x",
            "endpoint": "file:///etc/passwd",
        },
        {
            "provider": "openai-compatible",
            "name": "x",
            "endpoint": "https://user:pass@example.com/v1",
        },
        {
            "provider": "openai-compatible",
            "name": "x",
            "endpoint": "https://example.com/v1?token=fake",
        },
    ):
        response = client.post("/api/connections", json=payload)
        assert response.status_code == 422
        assert "not-real" not in response.text and "token=fake" not in response.text
    response = client.post(
        "/api/connections",
        json={"provider": "openrouter", "name": "x", "api_key": "not-real"},
    )
    cid = response.json()["id"]
    assert (
        client.patch(
            f"/api/connections/{cid}", json={"endpoint": "https://evil.example/v1"}
        ).status_code
        == 422
    )
    assert client.get("/api/connections").json()[-1]["endpoint"] == openrouter.BASE_URL


def test_execution_preserves_route_usage_and_rotated_key_version(
    client, upstream, monkeypatch
):
    cid = connect(client, upstream)
    mid = imported(client, cid)
    rid = run_with(client, mid).json()["id"]
    client.patch(f"/api/connections/{cid}", json={"api_key": "new-test-key"})
    client.post(f"/api/connections/{cid}/verify")
    calls = []

    def request(r):
        payload = json.loads(r.content)
        assert payload["provider"] == openrouter.DEFAULT_ROUTING
        assert payload["model"] == "maker/text" and "models" not in payload
        assert "usage" not in payload and "stream_options" not in payload
        assert r.headers["authorization"] == "Bearer new-test-key"
        assert str(r.url) == openrouter.BASE_URL + "/chat/completions"
        calls.append(payload)
        return httpx.Response(
            200,
            json={
                "id": "gen-test",
                "model": "maker/text-revision",
                "provider": "Test provider",
                "choices": [{"message": {"content": "hello"}, "finish_reason": "stop"}],
                "usage": {
                    "prompt_tokens": 5,
                    "completion_tokens": 2,
                    "total_tokens": 7,
                    "cost": 0.00002,
                },
            },
        )

    with httpx.Client(transport=httpx.MockTransport(request)) as transport:
        monkeypatch.setattr(
            "app.execution.generate",
            lambda config, messages, settings, key: generate(
                config, messages, settings, key, transport
            ),
        )
        data = execute_run(client, rid)
        execute_run(client, rid)
    result = data["items"][0]["result"]
    assert (
        len(calls) == 1
        and result["generation_id"] == "gen-test"
        and result["cost"] == "0.00002"
    )
    assert (
        result["upstream_provider"] == "Test provider"
        and result["credential_version"] == 2
    )
    assert data["snapshot"]["models"][0]["credential_version"] == 1
    assert "new-test-key" not in client.get(f"/api/runs/{rid}/export").text
    assert "gen-test" in client.get(f"/api/runs/{rid}/export?format=csv").text


@pytest.mark.parametrize(
    "status,code,retryable",
    [
        (401, "invalid_key", False),
        (402, "insufficient_credits", False),
        (429, "rate_limited", True),
        (503, "upstream_unavailable", True),
    ],
)
def test_http_errors_are_sanitized(status, code, retryable):
    with pytest.raises(ProviderError) as error:
        openrouter.check_response(
            httpx.Response(
                status,
                headers={"Retry-After": "12"},
                json={"error": {"message": "secret-never-store"}},
            )
        )
    assert error.value.code == code and error.value.retryable == retryable
    assert "secret" not in str(error.value)
    if retryable:
        assert error.value.retry_after == 12


def test_retry_after_long_limit_and_auth_invalidation(client, upstream, monkeypatch):
    cid = connect(client, upstream)
    mid = imported(client, cid)
    for error in [
        ProviderError("limit", True, "rate_limited", 120),
        ProviderError("invalid", False, "invalid_key"),
    ]:
        rid = run_with(client, mid).json()["id"]

        def fail(*_):
            raise error

        monkeypatch.setattr("app.execution.generate", fail)
        result = execute_run(client, rid)
        assert len(result["items"][0]["attempts"]) == 1
    assert client.get("/api/connections").json()[0]["status"] == "invalid"


def test_cancel_during_retry_wait_stops_new_calls(client, upstream, monkeypatch):
    cid = connect(client, upstream)
    mid = imported(client, cid)
    rid = run_with(client, mid).json()["id"]
    calls = []

    def fail(*_):
        calls.append(1)
        raise ProviderError("limit", True, "rate_limited", 4)

    monkeypatch.setattr("app.execution.generate", fail)
    monkeypatch.setattr(
        "app.execution.time.sleep", lambda _: client.post(f"/api/runs/{rid}/cancel")
    )
    assert execute_run(client, rid)["status"] == "cancelled" and len(calls) == 1


def test_timeout_is_not_automatically_retried_and_missing_cost_unknown():
    def timeout(r):
        raise httpx.ReadTimeout("secret request", request=r)

    config = {"provider": "openrouter", "model": "maker/text", "endpoint": "ignored"}
    settings = {"temperature": 0, "max_tokens": 8, "timeout": 5}
    with httpx.Client(transport=httpx.MockTransport(timeout)) as c:
        with pytest.raises(ProviderError) as e:
            generate(config, [], settings, "test-key", c)
    assert not e.value.retryable and e.value.code == "timeout_uncertain"
    assert e.value.diagnostics["timeout_kind"] == "ReadTimeout"
    assert e.value.diagnostics["configured_timeout_seconds"] == 5
    assert e.value.diagnostics["elapsed_ms"] >= 0
    with httpx.Client(
        transport=httpx.MockTransport(
            lambda r: httpx.Response(
                200, json={"choices": [{"message": {"content": "ok"}}]}
            )
        )
    ) as c:
        result = generate(config, [], settings, "test-key", c)
    assert (
        result["cost"] is None
        and result["input_tokens"] is None
        and result["upstream_provider"] is None
    )


def test_failed_item_preserves_safe_response_diagnostics(client, upstream, monkeypatch):
    cid = connect(client, upstream)
    mid = imported(client, cid)
    rid = run_with(client, mid).json()["id"]

    def no_text(*_):
        raise ProviderError(
            "上游回傳空白文字",
            code="no_text_output",
            diagnostics={
                "finish_reason": "length",
                "requested_max_tokens": 32768,
                "completion_tokens": 32768,
                "resolved_model": "maker/text",
            },
        )

    monkeypatch.setattr("app.execution.generate", no_text)
    item = execute_run(client, rid)["items"][0]
    assert item["status"] == "failed"
    assert item["result"] is None
    assert item["attempts"][0]["diagnostics"] == {
        "finish_reason": "length",
        "requested_max_tokens": 32768,
        "completion_tokens": 32768,
        "resolved_model": "maker/text",
    }


def test_metadata_transport_only_get(monkeypatch):
    original = httpx.Client
    calls = []

    def handle(request):
        calls.append(request.method)
        assert request.url.path == "/api/v1/key"
        return httpx.Response(200, json={"data": {"limit": None, "usage": 1}})

    monkeypatch.setattr(
        openrouter.httpx,
        "Client",
        lambda **kwargs: original(transport=httpx.MockTransport(handle), **kwargs),
    )
    assert openrouter.verify_key("fake-test-key")["limit"] is None
    assert calls == ["GET"]


def test_invalid_catalog_does_not_become_empty(monkeypatch):
    for raw in [
        [],
        {},
        [{"id": "test/model", "architecture": []}],
        [{"id": "test/model", "supported_parameters": "bad"}],
    ]:
        monkeypatch.setattr(openrouter, "get_metadata", lambda *_, value=raw: value)
        if raw == [{"id": "test/model", "architecture": []}]:
            continue  # an empty optional value is treated as absent
        with pytest.raises(ProviderError):
            openrouter.list_models("fake")
