"""Compare the latest attempt for each model on one immutable question bank."""

import json
from collections import Counter

from fastapi import HTTPException
from sqlalchemy import select

from .db import Dataset, Item, Run

ACTIVE = {"queued", "running", "cancelling"}


def _case_counts(cases):
    return Counter(json.dumps(case, ensure_ascii=False, sort_keys=True) for case in cases)


def dataset_ranking(db, reference):
    if reference.snapshot.get("retry_of"):
        original = db.get(Run, reference.snapshot["retry_of"])
        if original is not None:
            reference = original
    dataset_id = reference.snapshot.get("dataset_id")
    dataset = db.get(Dataset, dataset_id) if dataset_id else None
    if dataset is None:
        raise HTTPException(404, "這筆測試沒有可比較的題庫版本")

    datasets = (
        db.scalars(select(Dataset).where(Dataset.bundle_id == dataset.bundle_id)).all()
        if dataset.bundle_id else [dataset]
    )
    question_count = sum(len(part.cases) for part in datasets)
    dataset_ids = {part.id for part in datasets}
    expected = {part.id: _case_counts(part.cases) for part in datasets}
    runs = db.scalars(
        select(Run).where(
            Run.deleted_at.is_(None),
            Run.snapshot["dataset_id"].as_string().in_(dataset_ids),
        ).order_by(Run.created_at.desc(), Run.id.desc())
    ).all()

    groups = {}
    for run in runs:
        if run.snapshot.get("retry_of"):
            continue  # A retry contains only failed items, not the full question bank.
        settings = run.snapshot.get('settings', {})
        ref_settings = reference.snapshot.get('settings', {})
        if settings.get('bfcl_runtime') != ref_settings.get('bfcl_runtime'):
            continue
        if settings.get('coding_runtime') != ref_settings.get('coding_runtime'):
            continue
        if ref_settings.get('coding_runtime') and settings.get('code_timeout', 10) != ref_settings.get('code_timeout', 10):
            continue
        groups.setdefault(run.batch_id or run.id, []).append(run)

    latest_by_model = {}
    for parts in groups.values():
        actual = {part.id: Counter() for part in datasets}
        for run in parts:
            actual[run.snapshot["dataset_id"]].update(_case_counts(run.snapshot.get("cases", [])))
        if actual != expected:
            continue  # Never compare a subset with a complete question bank.
        for model in parts[0].snapshot.get("models", []):
            model_id = model["id"]
            stamp = max((part.created_at, part.id) for part in parts)
            if model_id not in latest_by_model or stamp > latest_by_model[model_id][0]:
                latest_by_model[model_id] = (stamp, parts, model)

    if not latest_by_model:
        return {
            "dataset_name": dataset.bundle_name or dataset.name,
            "question_count": question_count,
            "is_final": True,
            "models": [],
        }

    selected_run_ids = {
        part.id
        for _, parts, _ in latest_by_model.values()
        for part in parts
    }
    scores = {}
    run_ids_by_model = {}
    for model_id, (_, parts, model) in latest_by_model.items():
        run_ids_by_model[model_id] = {part.id for part in parts}
        scores[model_id] = {
            "model_id": model_id,
            "name": model["name"],
            "provider": model["provider"],
            "dynamic_model": model["provider"] == "openrouter"
            and (model.get("catalog") or {}).get("fixed_model") is False,
            "total": 0,
            "completed": 0,
            "failed": 0,
            "cancelled": 0,
            "graded": 0,
            "passed": 0,
            "categories": {},
            "provisional": any(part.status in ACTIVE for part in parts),
            "cancelled_run": any(part.status == "cancelled" for part in parts),
            "expected_total": question_count * parts[0].snapshot.get("settings", {}).get("repeats", 1),
        }

    snapshots = {run.id: run.snapshot for _, parts, _ in latest_by_model.values() for run in parts}
    for run_id, model_id, status, passed, case_index in db.execute(
        select(
            Item.run_id,
            Item.model_id,
            Item.status,
            Item.result["evaluation"]["passed"].as_boolean(),
            Item.case_index,
        ).where(Item.run_id.in_(selected_run_ids))
    ):
        if run_id not in run_ids_by_model.get(model_id, ()):
            continue
        score = scores[model_id]
        spec = snapshots[run_id]['cases'][case_index].get('rule', {}).get('bfcl')
        if spec and status == 'completed' and isinstance(passed, bool):
            category = score['categories'].setdefault(spec['category'], {'graded': 0, 'passed': 0})
            category['graded'] += 1
            category['passed'] += int(passed)
        score["total"] += 1
        if status == "completed":
            score["completed"] += 1
            if passed is True or passed is False:
                score["graded"] += 1
                score["passed"] += int(passed)
        elif status == "failed":
            score["failed"] += 1
        elif status == "cancelled":
            score["cancelled"] += 1

    ranked = []
    for score in scores.values():
        expected_total = score.pop("expected_total")
        score["pass_rate"] = (
            round(100 * score["passed"] / score["graded"], 1)
            if score["graded"] else None
        )
        # In-progress/cancelled samples may look perfect after only a few answers.
        score["ranked"] = (
            not score["provisional"] and not score["cancelled_run"]
            and score["graded"] > 0 and score["total"] > 0
            and score["total"] == expected_total
            and score["completed"] + score["failed"] + score["cancelled"] == score["total"]
        )
        if reference.snapshot.get('settings', {}).get('coding_runtime'):
            score['metric'] = 'pass@1' if score['ranked'] and score['graded'] == expected_total and expected_total == question_count else '已評分通過率'
            score['ranked'] = score['ranked'] and score['graded'] == expected_total
        if reference.snapshot.get('settings', {}).get('bfcl_runtime'):
            score['metric'] = '工具調用正確率'
            score['ranked'] = score['ranked'] and score['graded'] == expected_total and expected_total == question_count
        ranked.append(score)
    ranked.sort(key=lambda score: (
        not score["ranked"],
        -(score["pass_rate"] or 0),
        -score["graded"],
        score["name"].casefold(),
    ))
    return {
        "dataset_name": dataset.bundle_name or dataset.name,
        "question_count": question_count,
        "is_final": not any(score["provisional"] for score in ranked),
        "models": ranked,
    }
