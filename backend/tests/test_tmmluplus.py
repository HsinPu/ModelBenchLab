from app.evaluators import evaluate
import httpx

from app.tmmluplus import SUBJECTS, convert_csv, pinned_subjects


CSV = '''question,A,B,C,D,answer
"哪個是正確答案？","有,逗號",乙,丙,丁,A
第二題,甲,乙,丙,丁,C
第三題,甲,乙,丙,丁,D
'''


def test_catalog_and_official_preview(client, monkeypatch):
    assert len(SUBJECTS) == 66
    catalog = client.get("/api/benchmarks/tmmluplus")
    assert catalog.status_code == 200
    assert catalog.json()["revision"] == "v1.1"
    assert "computer_science" in catalog.json()["subjects"]

    calls = []
    def fake_download(subject, split, revision):
        calls.append((subject, split, revision))
        return CSV
    monkeypatch.setattr("app.tmmluplus.download_csv", fake_download)
    body = {"subject": "computer_science", "split": "validation", "limit": 2}
    first = client.post("/api/benchmarks/tmmluplus/preview", json=body)
    second = client.post("/api/benchmarks/tmmluplus/preview", json=body)
    assert first.status_code == 200
    assert first.json() == second.json()
    assert calls == [("computer_science", "validation", "v1.1")] * 2
    result = first.json()
    assert result["available"] == 3
    assert len(result["cases"]) == 2
    assert result["imported_from"] == "official_download"
    assert all(c["rule"]["kind"] == "choice" for c in result["cases"])
    assert all(c["source"]["revision"] == "v1.1" for c in result["cases"])
    assert all(c["source"]["url"].endswith("computer_science_val.csv") for c in result["cases"])

    saved = client.post("/api/datasets", json={"name": result["name"], "cases": result["cases"]})
    assert saved.status_code == 201
    stored = next(d for d in client.get("/api/datasets").json() if d["id"] == saved.json()["id"])
    assert stored["cases"][0]["source"]["dataset"] == "ikala/tmmluplus"


def test_latest_catalog_and_preview_pin_the_same_commit(client, monkeypatch):
    sha = "a" * 40
    files = [
        {"rfilename": f"data/{subject}_{split}.csv"}
        for subject in ("computer_science", "linear_algebra") for split in ("val", "test")
    ]
    metadata_calls = []
    def fake_get(url, **kwargs):
        metadata_calls.append(url)
        return httpx.Response(200, json={
            "id": "ikala/tmmluplus", "sha": sha, "lastModified": "2026-09-25T00:00:00Z", "siblings": files,
        }, request=httpx.Request("GET", url))
    downloaded = []
    def fake_download(subject, split, revision):
        downloaded.append((subject, split, revision))
        return CSV
    monkeypatch.setattr("app.tmmluplus.httpx.get", fake_get)
    monkeypatch.setattr("app.tmmluplus.download_csv", fake_download)
    pinned_subjects.cache_clear()
    try:
        latest = client.get("/api/benchmarks/tmmluplus/latest")
        assert latest.status_code == 200
        assert latest.json()["revision"] == sha
        assert latest.json()["subjects"] == ["computer_science", "linear_algebra"]
        response = client.post("/api/benchmarks/tmmluplus/preview", json={
            "subject": "linear_algebra", "split": "validation", "limit": 1, "revision": sha,
        })
        assert response.status_code == 200, response.text
        assert downloaded == [("linear_algebra", "validation", sha)]
        assert response.json()["revision"] == sha
        case = response.json()["cases"][0]
        assert case["source"]["revision"] == sha
        assert f"/blob/{sha}/data/linear_algebra_val.csv" in case["source"]["url"]
        assert metadata_calls == [f"https://huggingface.co/api/datasets/ikala/tmmluplus/revision/{ref}" for ref in ("main", sha)]
    finally:
        pinned_subjects.cache_clear()


def test_latest_rejects_invalid_metadata_and_unverified_upload(client, monkeypatch):
    url = "https://huggingface.co/api/datasets/ikala/tmmluplus/revision/main"
    monkeypatch.setattr("app.tmmluplus.httpx.get", lambda *_args, **_kwargs: httpx.Response(
        200, json={"id": "another/dataset", "sha": "a" * 40, "siblings": []},
        request=httpx.Request("GET", url),
    ))
    assert client.get("/api/benchmarks/tmmluplus/latest").status_code == 502
    assert client.post("/api/benchmarks/tmmluplus/preview", json={
        "subject": "computer_science", "revision": "../../main", "csv_text": CSV,
    }).status_code == 422


def test_uploaded_csv_and_invalid_inputs(client):
    body = {"subject": "computer_science", "split": "test", "limit": 100, "csv_text": CSV}
    response = client.post("/api/benchmarks/tmmluplus/preview", json=body)
    assert response.status_code == 200
    assert len(response.json()["cases"]) == 3
    assert response.json()["imported_from"] == "uploaded_csv"
    assert "有,逗號" in response.json()["cases"][0]["messages"][0]["content"]
    assert response.json()["cases"][0]["source"]["url"].endswith("computer_science_test.csv")

    assert client.post("/api/benchmarks/tmmluplus/preview", json={**body, "subject": "../evil"}).status_code == 422
    assert client.post("/api/benchmarks/tmmluplus/preview", json={**body, "limit": 1001}).status_code == 422
    assert client.post("/api/benchmarks/tmmluplus/preview", json={**body, "csv_text": "bad,data\nx,y"}).status_code == 422
    assert client.post("/api/benchmarks/tmmluplus/preview", json={**body, "csv_text": "question,A,B,C,D,answer\nx,a,b,c,d,\n"}).status_code == 422


def test_choice_evaluation_is_strict_about_final_format(client):
    rule = {"kind": "choice", "expected": "A"}
    assert evaluate("A", rule)["passed"] is True
    assert evaluate("答案：A", rule)["passed"] is True
    assert evaluate("答案是：A", rule)["passed"] is True
    assert evaluate("（A）", rule)["passed"] is True
    assert evaluate("B", rule)["passed"] is False
    assert evaluate("A，因為...", rule)["passed"] is False
    assert client.post("/api/datasets", json={"name": "bad", "cases": [{
        "title": "x", "messages": [{"role": "user", "content": "x"}],
        "rule": {"kind": "choice", "expected": "E"},
    }]}).status_code == 422


def test_too_many_cases_are_not_silently_truncated():
    result = convert_csv(CSV, "computer_science", "test", 1000, "uploaded_csv")
    assert result["available"] == len(result["cases"]) == 3


def test_complete_subject_preview_keeps_every_question(client):
    response = client.post("/api/benchmarks/tmmluplus/preview", json={
        "subject": "computer_science", "split": "test", "limit": None, "csv_text": CSV,
    })
    assert response.status_code == 200
    assert response.json()["available"] == len(response.json()["cases"]) == 3


def test_large_dataset_bundle_creates_one_click_run_batches(client):
    cases = [{
        "title": f"題目 {index}",
        "messages": [{"role": "user", "content": f"問題 {index}"}],
        "rule": {"kind": "choice", "expected": "A"},
        "source": {"dataset": "ikala/tmmluplus", "revision": "v1.1", "subject": "computer_science", "row": index + 2},
    } for index in range(1001)]
    created = client.post("/api/datasets/batch", json={"name": "TMMLU+ 完整測試", "cases": cases})
    assert created.status_code == 201, created.text
    bundle_id = created.json()["bundle_id"]
    assert created.json()["batches"] == 2
    listing = [row for row in client.get("/api/datasets").json() if row["bundle_id"] == bundle_id]
    assert len(listing) == 2
    assert sum(row["case_count"] for row in listing) == 1001
    assert all(row["cases"] == [] for row in listing)

    model = client.post("/api/models", json={
        "name": "demo", "provider": "demo", "model": "demo-stable", "api_key": "test",
    }).json()["id"]
    second_model = client.post("/api/models", json={
        "name": "demo 2", "provider": "demo", "model": "demo-experimental", "api_key": "test",
    }).json()["id"]
    prompt = client.post("/api/prompts", json={"name": "v1", "text": ""}).json()["id"]
    started = client.post("/api/run-batches", json={
        "name": "全科測試", "bundle_id": bundle_id,
        "model_ids": [model, second_model], "prompt_id": prompt, "repeats": 5,
    })
    assert started.status_code == 201, started.text
    assert started.json()["runs"] == 3
    assert started.json()["jobs"] == 10010
    details = [client.get(f"/api/runs/{run_id}").json() for run_id in started.json()["run_ids"]]
    assert sum(detail["total"] for detail in details) == 10010
    assert max(detail["total"] for detail in details) == 5000
    assert {detail["batch_id"] for detail in details} == {started.json()["batch_id"]}
    assert sum(len(detail["snapshot"]["cases"]) for detail in details) == 1001
