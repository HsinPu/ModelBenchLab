import asyncio
import csv
import io
import json
import os
from contextlib import asynccontextmanager
from uuid import uuid4
from collections import Counter
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.exceptions import RequestValidationError
from sqlalchemy import select, update
from .db import (
    Session,
    Model,
    ProviderConnection,
    Dataset,
    Prompt,
    Run,
    Item,
    Review,
    init_db,
    now,
)
from .schemas import ModelInput, DatasetInput, PromptInput, RunInput, ReviewInput
from .security import encrypt, cipher
from .connections import (
    router as connections_router,
    public_model,
    validate_model,
    execution_key,
)
from .providers import generate, ProviderError
from .execution import dispatch, reconcile
from .evaluators import evaluate
from .seed import seed


@asynccontextmanager
async def lifespan(app):
    cipher()
    init_db()
    if os.getenv("SEED_DEMO", "1") == "1":
        seed()
    yield


app = FastAPI(title="ModelBenchLab API", version="0.2.0", lifespan=lifespan)
app.include_router(connections_router)


@app.exception_handler(RequestValidationError)
async def validation_error(request, error):
    # Pydantic's input/context can echo whole bodies, including API keys.
    return JSONResponse(
        {
            "detail": [
                {"loc": e["loc"], "msg": e["msg"], "type": e["type"]}
                for e in error.errors()
            ]
        },
        status_code=422,
    )


@app.middleware("http")
async def same_origin_write(request: Request, call_next):
    # Local/private single-user MVP. Block browser cross-origin mutations.
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        from urllib.parse import urlsplit

        origin = request.headers.get("origin")
        if origin and urlsplit(origin).netloc != request.headers.get("host"):
            return JSONResponse({"detail": "跨來源寫入不被允許"}, status_code=403)
    return await call_next(request)


def required(db, cls, identifier):
    row = db.get(cls, identifier)
    if row is None:
        raise HTTPException(404, "找不到指定資料")
    return row


def run_summary(db, run):
    items = db.scalars(select(Item).where(Item.run_id == run.id)).all()
    counts = Counter(i.status for i in items)
    evaluations = [
        (i.result or {}).get("evaluation", {}).get("passed")
        for i in items
        if i.status == "completed"
    ]
    graded = [v for v in evaluations if v is not None]
    latencies = [i.result["latency_ms"] for i in items if i.result]
    return {
        "id": run.id,
        "name": run.name,
        "status": run.status,
        "created_at": run.created_at,
        "finished_at": run.finished_at,
        "total": len(items),
        "counts": dict(counts),
        "passed": sum(v is True for v in graded),
        "graded": len(graded),
        "pass_rate": round(100 * sum(v is True for v in graded) / len(graded), 1)
        if graded
        else None,
        "avg_latency_ms": round(sum(latencies) / len(latencies)) if latencies else None,
        "models": run.snapshot["models"],
        "dataset_name": run.snapshot["dataset_name"],
    }


def item_data(item):
    return {
        k: getattr(item, k)
        for k in (
            "id",
            "model_id",
            "case_index",
            "repeat_index",
            "status",
            "result",
            "attempts",
            "started_at",
            "finished_at",
        )
    }


@app.get("/api/health")
def health():
    with Session() as db:
        db.execute(select(1))
    return {
        "status": "ok",
        "version": "0.2.0",
        "task_mode": os.getenv("TASK_MODE", "local"),
    }


@app.get("/api/models")
def models():
    with Session() as db:
        return [
            public_model(m, db)
            for m in db.scalars(select(Model).order_by(Model.created_at))
        ]


@app.post("/api/models", status_code=201)
def create_model(body: ModelInput):
    with Session() as db:
        row = Model(
            id=str(uuid4()),
            **body.model_dump(exclude={"api_key"}),
            secret=encrypt(body.api_key),
        )
        if row.provider != "demo":
            connection = ProviderConnection(
                id=str(uuid4()),
                name=row.name,
                provider=row.provider,
                endpoint=row.endpoint,
                secret=row.secret,
            )
            db.add(connection)
            db.flush()
            row.connection_id, row.secret = connection.id, ""
        db.add(row)
        db.commit()
        return public_model(row, db)


@app.post("/api/models/{identifier}/test")
def test_model(identifier: str):
    with Session() as db:
        row = required(db, Model, identifier)
        settings = {"temperature": 0, "max_tokens": 8, "timeout": 15}
        config = validate_model(db, row, settings)
        version = None
        try:
            key, version = execution_key(db, config, row)
            db.commit()
            result = generate(
                config, [{"role": "user", "content": "Reply OK"}], settings, key
            )
            return {"ok": True, **result, "credential_version": version}
        except ProviderError as e:
            if row.connection_id and e.code in ("invalid_key", "forbidden"):
                db.execute(
                    update(ProviderConnection)
                    .where(
                        ProviderConnection.id == row.connection_id,
                        ProviderConnection.credential_version == version,
                    )
                    .values(status="invalid", error=str(e))
                )
                db.commit()
            raise HTTPException(502, str(e))


@app.get("/api/datasets")
def datasets():
    with Session() as db:
        return [
            {"id": d.id, "name": d.name, "cases": d.cases, "created_at": d.created_at}
            for d in db.scalars(select(Dataset).order_by(Dataset.created_at.desc()))
        ]


@app.post("/api/datasets", status_code=201)
def create_dataset(body: DatasetInput):
    with Session() as db:
        row = Dataset(
            id=str(uuid4()),
            name=body.name,
            cases=[c.model_dump(by_alias=True) for c in body.cases],
        )
        db.add(row)
        db.commit()
        return {"id": row.id}


@app.get("/api/prompts")
def prompts():
    with Session() as db:
        return [
            {"id": p.id, "name": p.name, "text": p.text}
            for p in db.scalars(select(Prompt).order_by(Prompt.created_at.desc()))
        ]


@app.post("/api/prompts", status_code=201)
def create_prompt(body: PromptInput):
    with Session() as db:
        row = Prompt(id=str(uuid4()), **body.model_dump())
        db.add(row)
        db.commit()
        return {"id": row.id}


@app.get("/api/runs")
def runs():
    with Session() as db:
        return [
            run_summary(db, r)
            for r in db.scalars(select(Run).order_by(Run.created_at.desc()).limit(100))
        ]


@app.post("/api/runs", status_code=201)
def create_run(body: RunInput):
    with Session() as db:
        dataset = required(db, Dataset, body.dataset_id)
        prompt = required(db, Prompt, body.prompt_id)
        selected = [
            validate_model(db, required(db, Model, mid), body.model_dump())
            for mid in body.model_ids
        ]
        if len(dataset.cases) * len(selected) * body.repeats > 5000:
            raise HTTPException(422, "單次測試最多 5000 個工作項目")
        snapshot = {
            "version": 2,
            "dataset_id": dataset.id,
            "dataset_name": dataset.name,
            "cases": dataset.cases,
            "prompt": {"id": prompt.id, "name": prompt.name, "text": prompt.text},
            "models": selected,
            "settings": body.model_dump(
                include={"repeats", "temperature", "max_tokens", "timeout"}
            ),
        }
        run = Run(id=str(uuid4()), name=body.name, snapshot=snapshot)
        db.add(run)
        db.flush()
        ids = []
        for model in selected:
            for index in range(len(dataset.cases)):
                for repeat in range(body.repeats):
                    item = Item(
                        id=str(uuid4()),
                        run_id=run.id,
                        model_id=model["id"],
                        case_index=index,
                        repeat_index=repeat,
                    )
                    db.add(item)
                    ids.append(item.id)
        db.commit()
        result = run_summary(db, run)
    try:
        dispatch(ids)
    except Exception:
        result["dispatch_warning"] = "佇列暫時無法連線，排程器恢復後將重新派送"
    return result


@app.get("/api/runs/{identifier}")
def run_detail(identifier: str):
    with Session() as db:
        run = required(db, Run, identifier)
        items = db.scalars(
            select(Item)
            .where(Item.run_id == identifier)
            .order_by(Item.case_index, Item.repeat_index, Item.model_id)
        ).all()
        reviews = db.scalars(
            select(Review)
            .join(Item, Review.item_id == Item.id)
            .where(Item.run_id == identifier)
            .order_by(Review.created_at)
        ).all()
        return {
            **run_summary(db, run),
            "snapshot": run.snapshot,
            "items": [item_data(i) for i in items],
            "reviews": [
                {
                    "item_id": r.item_id,
                    "score": r.score,
                    "note": r.note,
                    "created_at": r.created_at,
                }
                for r in reviews
            ],
        }


@app.post("/api/runs/{identifier}/cancel")
def cancel_run(identifier: str):
    with Session() as db:
        run = required(db, Run, identifier)
        if run.status not in ("queued", "running", "cancelling"):
            raise HTTPException(409, "此測試已結束")
        run.status = "cancelling"
        db.execute(
            update(Item)
            .where(Item.run_id == identifier, Item.status == "queued")
            .values(status="cancelled", finished_at=now())
        )
        db.commit()
    reconcile(identifier)
    return {"ok": True}


@app.post("/api/runs/{identifier}/retry", status_code=201)
def retry_run(identifier: str):
    with Session() as db:
        old = required(db, Run, identifier)
        if old.status in ("queued", "running", "cancelling"):
            raise HTTPException(409, "請等待測試結束")
        failed = db.scalars(
            select(Item).where(Item.run_id == identifier, Item.status == "failed")
        ).all()
        if not failed:
            raise HTTPException(409, "沒有失敗工作可重跑")
        for mid in {i.model_id for i in failed}:
            validate_model(db, required(db, Model, mid), old.snapshot["settings"])
        new = Run(
            id=str(uuid4()),
            name=(old.name[:100] + " · 重跑"),
            snapshot={**old.snapshot, "retry_of": old.id},
        )
        db.add(new)
        db.flush()
        ids = []
        for i in failed:
            j = Item(
                id=str(uuid4()),
                run_id=new.id,
                model_id=i.model_id,
                case_index=i.case_index,
                repeat_index=i.repeat_index,
            )
            db.add(j)
            ids.append(j.id)
        db.commit()
    try:
        dispatch(ids)
    except Exception:
        pass
    return {"id": new.id}


@app.post("/api/items/{identifier}/review", status_code=201)
def review(identifier: str, body: ReviewInput):
    with Session() as db:
        item = required(db, Item, identifier)
        if item.status != "completed":
            raise HTTPException(409, "此項目尚無回答")
        db.add(Review(id=str(uuid4()), item_id=item.id, **body.model_dump()))
        db.commit()
    return {"ok": True}


@app.post("/api/items/{identifier}/evaluate")
def re_evaluate(identifier: str):
    with Session() as db:
        item = required(db, Item, identifier)
        if not item.result:
            raise HTTPException(409, "此項目尚無回答")
        run = db.get(Run, item.run_id)
        item.result = {
            **item.result,
            "evaluation": evaluate(
                item.result["output"], run.snapshot["cases"][item.case_index]["rule"]
            ),
        }
        db.commit()
    return {"ok": True}


@app.get("/api/runs/{identifier}/export")
def export(identifier: str, format: str = "json"):
    data = run_detail(identifier)
    if format == "json":
        return JSONResponse(
            data,
            headers={
                "Content-Disposition": 'attachment; filename="run-'
                + identifier
                + '.json"'
            },
        )
    if format != "csv":
        raise HTTPException(422, "僅支援 json 或 csv")
    stream = io.StringIO()
    writer = csv.writer(stream)
    writer.writerow(
        [
            "case",
            "model",
            "repeat",
            "status",
            "output",
            "passed",
            "latency_ms",
            "error",
            "requested_model",
            "resolved_model",
            "upstream_provider",
            "generation_id",
            "cost_usd",
            "credential_version",
        ]
    )

    def cell(value):
        text = str(value if value is not None else "")
        return "'" + text if text.lstrip().startswith(("=", "+", "-", "@")) else text

    names = {m["id"]: m["name"] for m in data["models"]}
    for i in data["items"]:
        result = i["result"] or {}
        writer.writerow(
            [
                cell(v)
                for v in [
                    data["snapshot"]["cases"][i["case_index"]]["title"],
                    names[i["model_id"]],
                    i["repeat_index"] + 1,
                    i["status"],
                    result.get("output"),
                    result.get("evaluation", {}).get("passed"),
                    result.get("latency_ms"),
                    (i["attempts"][-1].get("error", "") if i["attempts"] else ""),
                    result.get("requested_model"),
                    result.get("resolved_model"),
                    result.get("upstream_provider"),
                    result.get("generation_id"),
                    result.get("cost"),
                    result.get("credential_version"),
                ]
            ]
        )
    return StreamingResponse(
        iter(["\ufeff" + stream.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": 'attachment; filename="run-' + identifier + '.csv"'
        },
    )


@app.get("/api/runs/{identifier}/events")
async def events(identifier: str, request: Request):
    with Session() as db:
        required(db, Run, identifier)

    async def stream():
        while not await request.is_disconnected():
            with Session() as db:
                payload = run_summary(db, db.get(Run, identifier))
            yield "data: " + json.dumps(payload) + "\n\n"
            if payload["status"] not in ("queued", "running", "cancelling"):
                break
            await asyncio.sleep(1)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
