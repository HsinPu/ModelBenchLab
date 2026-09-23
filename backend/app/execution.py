import time
from datetime import datetime, timezone, timedelta
from sqlalchemy import select, update
from .db import Session, Run, Item, Model, ProviderConnection, now, init_db
from .providers import generate, ProviderError
from .connections import execution_key
from .evaluators import evaluate

TERMINAL = ("completed", "failed", "cancelled")


def wait_for_retry(db, run, delay):
    # Short sleeps keep cancellation responsive without holding a DB transaction.
    remaining = delay
    while remaining > 0:
        db.commit()
        step = min(0.5, remaining)
        time.sleep(step)
        remaining -= step
        db.refresh(run)
        if run.status in ("cancelling", "cancelled"):
            return False
    return True


def reconcile(run_id):
    with Session() as db:
        run = db.get(Run, run_id)
        items = db.scalars(select(Item).where(Item.run_id == run_id)).all()
        if all(i.status in TERMINAL for i in items):
            run.status = (
                "cancelled"
                if run.status in ("cancelling", "cancelled")
                else (
                    "completed_with_errors"
                    if any(i.status == "failed" for i in items)
                    else "completed"
                )
            )
            run.finished_at = now()
            db.commit()


def execute_item(item_id):
    with Session() as db:
        claimed = db.execute(
            update(Item)
            .where(Item.id == item_id, Item.status == "queued")
            .values(status="running", started_at=now())
        )
        if not claimed.rowcount:
            return
        db.commit()
        item = db.get(Item, item_id)
        run = db.get(Run, item.run_id)
        run_id = run.id
        if run.status in ("cancelled", "cancelling"):
            item.status = "cancelled"
            item.finished_at = now()
            db.commit()
            reconcile(run_id)
            return
        db.execute(
            update(Run)
            .where(Run.id == run_id, Run.status == "queued")
            .values(status="running")
        )
        db.commit()
        snapshot = run.snapshot
        config = next(m for m in snapshot["models"] if m["id"] == item.model_id)
        model = db.get(Model, item.model_id)
        case = snapshot["cases"][item.case_index]
        messages = (
            [{"role": "system", "content": snapshot["prompt"]["text"]}]
            if snapshot["prompt"]["text"]
            else []
        ) + case["messages"]
        settings = snapshot["settings"]
        attempts = []
        result = None
        for attempt in range(3):
            credential_version = None
            db.refresh(run)
            if run.status in ("cancelling", "cancelled"):
                break
            try:
                key, credential_version = execution_key(db, config, model)
                db.commit()
                result = generate(config, messages, settings, key)
                result["credential_version"] = credential_version
                attempts.append(
                    {
                        "number": attempt + 1,
                        "at": now(),
                        "status": "completed",
                        "credential_version": credential_version,
                    }
                )
                break
            except ProviderError as error:
                attempts.append(
                    {
                        "number": attempt + 1,
                        "at": now(),
                        "status": "failed",
                        "error": str(error),
                        "code": error.code,
                        "retry_after": error.retry_after,
                    }
                )
                cid = config.get("connection_id") or model.connection_id
                if cid and error.code in ("invalid_key", "forbidden"):
                    db.execute(
                        update(ProviderConnection)
                        .where(
                            ProviderConnection.id == cid,
                            ProviderConnection.credential_version == credential_version,
                        )
                        .values(status="invalid", error=str(error))
                    )
                item.attempts = list(attempts)
                db.commit()
                if not error.retryable or attempt == 2:
                    break
                delay = (
                    error.retry_after if error.retry_after is not None else 2**attempt
                )
                # Do not retry earlier than requested. Long rate limits need a manual rerun.
                if delay > 30 or not wait_for_retry(db, run, delay):
                    break
            except Exception:
                attempts.append(
                    {
                        "number": attempt + 1,
                        "at": now(),
                        "status": "failed",
                        "error": "執行失敗，請檢查後端設定及加密金鑰",
                    }
                )
                break
        db.refresh(run)
        if result is not None:
            try:
                result["evaluation"] = evaluate(result["output"], case["rule"])
            except Exception:
                result["evaluation"] = {
                    "passed": None,
                    "reason": "評分失敗，可重新評分",
                    "error": True,
                }
            item.result = result
            item.status = "completed"
        else:
            item.status = (
                "cancelled" if run.status in ("cancelling", "cancelled") else "failed"
            )
        item.attempts = attempts
        item.finished_at = now()
        db.commit()
    reconcile(run_id)


def recover_stale():
    # Do not automatically replay uncertain calls: the provider may have charged them.
    with Session() as db:
        cutoff = (datetime.now(timezone.utc) - timedelta(minutes=12)).isoformat()
        stale = db.scalars(
            select(Item).where(Item.status == "running", Item.started_at < cutoff)
        ).all()
        ids = set()
        for item in stale:
            item.status = "failed"
            item.finished_at = now()
            item.attempts = item.attempts + [
                {
                    "status": "failed",
                    "error": "Worker 中斷或工作逾期；請手動重跑，避免重複計費",
                }
            ]
            ids.add(item.run_id)
        db.commit()
    for run_id in ids:
        reconcile(run_id)


def dispatch(ids):
    import os

    if os.getenv("TASK_MODE", "local") == "celery":
        from .tasks import run_item

        for item_id in ids:
            run_item.delay(item_id)


def local_worker():
    init_db()
    print("ModelBenchLab local worker ready", flush=True)
    while True:
        recover_stale()
        with Session() as db:
            ids = db.scalars(
                select(Item.id).where(Item.status == "queued").limit(10)
            ).all()
        for item_id in ids:
            execute_item(item_id)
        time.sleep(0.5)


if __name__ == "__main__":
    local_worker()
