import asyncio
import json
import time
from contextlib import suppress
import httpx
from .openrouter import validate_key
from .openrouter import ProviderError, BASE_URL, DEFAULT_ROUTING, check_response, price


async def _cancellable_post(endpoint, headers, payload, timeout, cancelled):
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
        if cancelled():
            raise ProviderError("測試已強制取消", code="force_cancelled")
        request = asyncio.create_task(
            client.post(endpoint + "/chat/completions", headers=headers, json=payload)
        )
        try:
            while True:
                if cancelled():
                    request.cancel()
                    with suppress(asyncio.CancelledError):
                        await request
                    raise ProviderError("測試已強制取消", code="force_cancelled")
                done, _ = await asyncio.wait({request}, timeout=0.5)
                if done:
                    return await request
        finally:
            if not request.done():
                request.cancel()
                with suppress(asyncio.CancelledError):
                    await request


def generate(config, messages, settings, key="", client=None):
    start = time.perf_counter()
    if config["provider"] == "demo":
        text = messages[-1]["content"]
        answers = {
            "2 + 2": "4",
            "法國": "巴黎",
            "JSON": '{"name":"Alice","age":30}',
            "Python": "Python 是一種程式語言。",
            "翻譯": "Hello",
            "水": "H2O",
            "排序": "1, 2, 3",
            "首都": "東京",
            "布林": "true",
            "摘要": "本工具協助比較模型的品質與效能。",
        }
        answer = next(
            (v for k, v in answers.items() if k in text),
            "這是示範回答，請接入真實模型進行正式評估。",
        )
        if config["model"] == "demo-experimental" and any(
            k in text for k in ["2 + 2", "JSON", "翻譯"]
        ):
            answer = "示範：此模型未符合預期答案。"
        time.sleep(0.12 if config["model"] == "demo-stable" else 0.06)
        return {
            "output": answer,
            "latency_ms": round((time.perf_counter() - start) * 1000),
            "input_tokens": None,
            "output_tokens": None,
            "finish_reason": "stop",
            "demo": True,
        }
    validate_key(key)
    cancelled = settings.get("_force_cancelled")
    cancellable = client is None and callable(cancelled)
    own = client is None and not cancellable
    if own:
        client = httpx.Client(timeout=settings["timeout"], follow_redirects=False)
    try:
        routed = config["provider"] == "openrouter"
        catalog = config.get("catalog") if routed else None
        supported = (
            catalog.get("supported_parameters") if isinstance(catalog, dict) else None
        )
        payload = {"model": config["model"], "messages": messages, "stream": False}
        if settings.get('_bfcl'):
            from .bfcl import tools_for
            payload['tools'] = tools_for(settings['_bfcl'])
            payload['tool_choice'] = 'auto'
        if supported is None or "temperature" in supported:
            payload["temperature"] = settings["temperature"]
        if supported is None or "max_tokens" in supported:
            payload["max_tokens"] = settings["max_tokens"]
        headers = {"Authorization": "Bearer " + key} if key else {}
        if routed:
            # Dynamic IDs select a model upstream; a fixed-provider policy would
            # interfere with that selection. The requested ID stays in the snapshot.
            if not isinstance(catalog, dict) or catalog.get("fixed_model", True):
                payload["provider"] = {**(config.get("routing") or {}), **DEFAULT_ROUTING}
            headers["X-OpenRouter-Title"] = "ModelBenchLab"
        effort = config.get("reasoning_effort")
        if effort:
            if routed:
                payload["reasoning"] = {"effort": effort}
            else:
                payload["reasoning_effort"] = effort
        endpoint = BASE_URL if routed else config["endpoint"].rstrip("/")
        response = (
            asyncio.run(
                _cancellable_post(endpoint, headers, payload, settings["timeout"], cancelled)
            )
            if cancellable
            else client.post(endpoint + "/chat/completions", headers=headers, json=payload)
        )
        try:
            check_response(response)
        except ProviderError as error:
            if effort and error.code == "invalid_request":
                raise ProviderError(
                    f"模型服務拒絕請求；可能不支援思考程度 {effort}，也請檢查其他參數",
                    code="invalid_request",
                ) from None
            raise
        data = response.json()
        choice = data["choices"][0]
        usage = data.get("usage") or {}
        if not isinstance(usage, dict):
            raise ValueError("Invalid usage")
        reported_charge = price(usage.get("cost")) if routed else None

        def token(field):
            value = usage.get(field)
            return (
                value
                if isinstance(value, int) and not isinstance(value, bool) and value >= 0
                else None
            )

        def identifier(field):
            value = data.get(field)
            return value[:300] if isinstance(value, str) else None

        output = choice["message"].get("content")
        calls = []
        if settings.get('_bfcl'):
            raw_calls = choice['message'].get('tool_calls') or []
            if not isinstance(raw_calls, list) or len(raw_calls) > 100:
                raise ValueError('invalid tool calls')
            for call in raw_calls:
                function = call['function']
                if call.get('type') != 'function' or not isinstance(function.get('name'), str) or not isinstance(function.get('arguments'), str):
                    raise ValueError('invalid function response')
                if len(function['name']) > 200 or len(function['arguments']) > 200000:
                    raise ValueError('tool call too large')
                calls.append({'name': function['name'], 'arguments': function['arguments']})
            if calls and (output is None or (isinstance(output, str) and not output.strip())):
                output = json.dumps(calls, ensure_ascii=False, indent=2)
        if output is None or (isinstance(output, str) and not output.strip()):
            token_details = (
                usage.get("completion_tokens_details")
                or usage.get("output_tokens_details")
                or {}
            )
            if not isinstance(token_details, dict):
                token_details = {}
            reasoning_tokens = token_details.get("reasoning_tokens")
            diagnostics = {
                "finish_reason": str(choice.get("finish_reason") or "unknown")[:40],
                "http_status": response.status_code,
                "requested_max_tokens": payload.get("max_tokens"),
                "completion_tokens": token("completion_tokens"),
                "reasoning_tokens": reasoning_tokens
                if isinstance(reasoning_tokens, int)
                and not isinstance(reasoning_tokens, bool)
                and reasoning_tokens >= 0
                else None,
                "resolved_model": identifier("model"),
                "elapsed_ms": round((time.perf_counter() - start) * 1000),
                "reported_cost_usd": reported_charge,
            }
            if choice.get("finish_reason") == "length":
                raise ProviderError(
                    "上游回傳空白文字，並表示輸出達到長度限制；請查看實際模型與 Token 診斷資訊",
                    code="no_text_output",
                    diagnostics=diagnostics,
                )
            raise ProviderError(
                "上游回傳空白文字；請查看模型與回應診斷資訊",
                code="no_text_output",
                diagnostics=diagnostics,
            )
        if not isinstance(output, str):
            raise ProviderError(
                "模型回傳非文字內容，目前只支援 chat/completions 文字回答",
                code="non_text_output",
                diagnostics={"reported_cost_usd": reported_charge},
            )
        return {
            "output": output,
            **({'tool_calls': calls} if settings.get('_bfcl') else {}),
            "latency_ms": round((time.perf_counter() - start) * 1000),
            "input_tokens": token("prompt_tokens"),
            "output_tokens": token("completion_tokens"),
            "total_tokens": token("total_tokens"),
            "finish_reason": choice.get("finish_reason"),
            "demo": False,
            "requested_model": config["model"],
            "resolved_model": identifier("model"),
            "upstream_provider": identifier("provider"),
            "generation_id": identifier("id"),
            "cost": reported_charge,
            "cost_source": "openrouter_usage"
            if reported_charge is not None
            else None,
            "routing": payload.get("provider"),
        }
    except httpx.TimeoutException as error:
        raise ProviderError(
            "模型連線或網路讀寫等待逾時；上游可能已執行並計費，請手動確認後重跑",
            code="timeout_uncertain",
            diagnostics={
                "timeout_kind": type(error).__name__,
                "configured_timeout_seconds": settings["timeout"],
                "elapsed_ms": round((time.perf_counter() - start) * 1000),
            },
        )
    except httpx.RequestError:
        raise ProviderError(
            "連線中斷；上游可能已收到請求，請手動確認後重跑",
            code="connection_uncertain",
        )
    except (KeyError, IndexError, ValueError, TypeError, AttributeError):
        raise ProviderError(
            "模型回應格式不符合 chat/completions 工具格式" if settings.get('_bfcl') else "模型回應格式不符合 chat/completions 文字格式",
            diagnostics={'reported_cost_usd': reported_charge} if 'reported_charge' in locals() else {},
        )
    finally:
        if own:
            client.close()
