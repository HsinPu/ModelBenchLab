"""OpenRouter metadata adapter. It never generates text during verification."""

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from email.utils import parsedate_to_datetime
import httpx

BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_ROUTING = {"allow_fallbacks": False, "require_parameters": True}


class ProviderError(Exception):
    def __init__(
        self, message, retryable=False, code="provider_error", retry_after=None,
        diagnostics=None,
    ):
        super().__init__(message)
        self.retryable = retryable
        self.code = code
        self.retry_after = retry_after
        self.diagnostics = diagnostics or {}


def retry_delay(value):
    if not value:
        return None
    try:
        seconds = float(value)
    except (ValueError, TypeError):
        try:
            seconds = (
                parsedate_to_datetime(value) - datetime.now(timezone.utc)
            ).total_seconds()
        except (ValueError, TypeError, OverflowError):
            return None
    return max(0, seconds) if 0 <= seconds < float("inf") else None


def check_response(response):
    try:
        body = response.json()
    except ValueError:
        body = {}
    error = body.get("error") if isinstance(body, dict) else None
    if response.status_code < 400 and not error:
        return
    error = error if isinstance(error, dict) else {}
    status = response.status_code
    if status < 400:
        try:
            status = int(error.get("code", 502))
        except (ValueError, TypeError):
            status = 502
    delay = retry_delay(response.headers.get("Retry-After"))
    metadata = error.get("metadata") or {}
    source = metadata.get("limit_source") if isinstance(metadata, dict) else None
    if status == 401:
        raise ProviderError(
            "API Key 無效或已撤銷，請更新金鑰並重新驗證", code="invalid_key"
        )
    if status == 403:
        raise ProviderError("此金鑰沒有存取權限，請檢查廠商設定", code="forbidden")
    if status == 402:
        if source == "openrouter_in_flight_budget":
            raise ProviderError(
                "進行中的請求暫時占用額度，稍後重試", True, "in_flight_budget", delay
            )
        raise ProviderError(
            "帳戶餘額或金鑰額度不足，請至 OpenRouter 檢查", code="insufficient_credits"
        )
    if status == 429:
        raise ProviderError(
            "廠商暫時限流，請降低請求頻率或稍後再試", True, "rate_limited", delay
        )
    if status >= 500:
        raise ProviderError("模型服務暫時無法使用", True, "upstream_unavailable", delay)
    raise ProviderError(
        f"模型服務拒絕請求（HTTP {status}），請檢查模型與參數", code="invalid_request"
    )


def validate_key(key):
    if key and any(ord(c) < 33 or ord(c) > 126 for c in key):
        raise ProviderError(
            "API Key 格式不正確，請移除空白或非英文符號", code="invalid_key_format"
        )


def get_metadata(path, key):
    validate_key(key)
    try:
        with httpx.Client(timeout=25, follow_redirects=False) as client:
            response = client.get(
                BASE_URL + path,
                headers={"Authorization": "Bearer " + key} if key else {},
            )
        check_response(response)
        data = response.json()
        if not isinstance(data, dict) or "data" not in data:
            raise ValueError()
        return data["data"]
    except httpx.TimeoutException:
        raise ProviderError("OpenRouter 連線逾時，請稍後再試", True, "timeout")
    except httpx.RequestError:
        raise ProviderError(
            "無法連線到 OpenRouter，請檢查網路", True, "connection_error"
        )
    except (ValueError, TypeError):
        raise ProviderError("OpenRouter 回傳的資料格式不正確", code="invalid_response")


def verify_key(key):
    data = get_metadata("/key", key)
    if not isinstance(data, dict) or not any(
        k in data for k in ("limit", "usage", "is_free_tier")
    ):
        raise ProviderError("OpenRouter 金鑰資訊格式不正確", code="invalid_response")
    # Allowlist fields; never persist upstream headers, labels or arbitrary metadata.
    return {
        k: data.get(k)
        for k in (
            "limit",
            "limit_remaining",
            "limit_reset",
            "usage",
            "usage_daily",
            "usage_monthly",
            "is_free_tier",
        )
    }


def fixed_model(model_id):
    return bool(
        model_id
        and "/" in model_id
        and not model_id.startswith(("~", "openrouter/"))
        and not model_id.endswith((":online", ":nitro", ":floor"))
    )


def price(value):
    try:
        result = Decimal(str(value))
        return str(result) if result.is_finite() and result >= 0 else None
    except (InvalidOperation, TypeError, ValueError):
        return None


def list_models(key):
    raw = get_metadata("/models", key)
    if not isinstance(raw, list) or not raw:
        raise ProviderError(
            "模型目錄為空或格式不正確，保留上次同步資料", code="invalid_catalog"
        )
    models = []
    seen = set()
    for model in raw:
        if (
            not isinstance(model, dict)
            or not isinstance(model.get("id"), str)
            or not model["id"]
            or len(model["id"]) > 200
        ):
            raise ProviderError(
                "模型目錄包含無效資料，保留上次同步資料", code="invalid_catalog"
            )
        mid = model["id"]
        if mid in seen:
            continue
        seen.add(mid)
        architecture = model.get("architecture") or {}
        prices = model.get("pricing") or {}
        top = model.get("top_provider") or {}
        if not all(isinstance(v, dict) for v in (architecture, prices, top)):
            raise ProviderError(
                "模型目錄格式不正確，保留上次同步資料", code="invalid_catalog"
            )
        inputs = architecture.get("input_modalities") or []
        outputs = architecture.get("output_modalities") or []
        params = model.get("supported_parameters") or []
        if not all(
            isinstance(v, list) and all(isinstance(s, str) for s in v)
            for v in (inputs, outputs, params)
        ):
            raise ProviderError(
                "模型能力格式不正確，保留上次同步資料", code="invalid_catalog"
            )
        models.append(
            {
                "model_id": mid,
                "name": str(model.get("name") or mid)[:300],
                "author": mid.split("/")[0][:100],
                "details": {
                    "context_length": model.get("context_length"),
                    "max_completion_tokens": top.get("max_completion_tokens"),
                    "input_modalities": inputs,
                    "output_modalities": outputs,
                    "supported_parameters": params,
                    "pricing": {
                        k: price(prices.get(k))
                        for k in ("prompt", "completion", "request", "image")
                    },
                    "text_compatible": "text" in inputs and "text" in outputs,
                    "fixed_model": fixed_model(mid),
                },
            }
        )
    return models
