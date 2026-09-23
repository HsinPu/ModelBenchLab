import json
from concurrent.futures import ThreadPoolExecutor
import httpx
import pytest
from sqlalchemy import select
from app import openrouter
from app.db import Session, Model, ProviderConnection, CatalogModel
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
        "top_provider": {"max_completion_tokens": 1024},
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
    assert (
        client.post(
            f"/api/connections/{cid}/models", json={"model_ids": ["openrouter/auto"]}
        ).status_code
        == 422
    )
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
    original = client.get("/api/models").json()[0]
    upstream[0][:] = [entry("maker/paid")]
    assert client.post(f"/api/connections/{cid}/sync?force=true").status_code == 200
    current = client.get("/api/models").json()[0]
    assert current["id"] == mid and not current["available"] and original["available"]
    assert run_with(client, mid).status_code == 409


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
