"""Summarize provider-reported charges without inventing catalog-price totals."""

from decimal import Decimal, InvalidOperation


def reported_cost(result, provider):
    if provider != "openrouter" or not isinstance(result, dict):
        return None
    if result.get("cost_source") not in (None, "openrouter_usage"):
        return None
    value = result.get("cost")
    if value is None or isinstance(value, bool):
        return None
    try:
        cost = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    return cost if cost.is_finite() and cost >= 0 else None


def summarize_costs(items, models):
    providers = {model["id"]: model.get("provider") for model in models}
    totals = {
        model["id"]: {"amount": Decimal(0), "reported_items": 0, "unknown_items": 0}
        for model in models
        if model.get("provider") != "demo"
    }
    for item in items:
        if item.model_id not in totals:
            continue
        entry = totals[item.model_id]
        cost = reported_cost(item.result, providers[item.model_id])
        failed_attempts = [a for a in (item.attempts or []) if a.get("status") == "failed"]
        attempt_costs = [
            reported_cost(
                {"cost": (a.get("diagnostics") or {}).get("reported_cost_usd")},
                providers[item.model_id],
            )
            for a in failed_attempts
        ]
        charges = [charge for charge in [cost, *attempt_costs] if charge is not None]
        if charges:
            entry["amount"] += sum(charges, Decimal(0))
            entry["reported_items"] += 1
        if (item.status == "completed" and cost is None) or (
            item.status == "failed" and not charges
        ) or (
            item.status == "cancelled" and item.started_at is not None and not charges
        ) or any(charge is None for charge in attempt_costs):
            # Prior failed attempts or interrupted calls can have unreported charges.
            entry["unknown_items"] += 1

    def public(entry):
        return {
            "reported_usd": format(entry["amount"], "f"),
            "reported_items": entry["reported_items"],
            "unknown_items": entry["unknown_items"],
        }

    return {
        "reported_usd": format(sum((v["amount"] for v in totals.values()), Decimal(0)), "f"),
        "reported_items": sum(v["reported_items"] for v in totals.values()),
        "unknown_items": sum(v["unknown_items"] for v in totals.values()),
        "by_model": {model_id: public(value) for model_id, value in totals.items()},
    }
