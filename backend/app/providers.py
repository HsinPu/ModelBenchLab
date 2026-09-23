import time
import httpx
from .openrouter import validate_key
from .openrouter import ProviderError, BASE_URL, DEFAULT_ROUTING, check_response, price


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
    own = client is None
    client = client or httpx.Client(timeout=settings["timeout"], follow_redirects=False)
    try:
        routed = config["provider"] == "openrouter"
        payload = {
            "model": config["model"],
            "messages": messages,
            "temperature": settings["temperature"],
            "max_tokens": settings["max_tokens"],
            "stream": False,
        }
        headers = {"Authorization": "Bearer " + key} if key else {}
        if routed:
            # Fixed model and explicit provider policy are part of the run snapshot.
            payload["provider"] = {**(config.get("routing") or {}), **DEFAULT_ROUTING}
            headers["X-OpenRouter-Title"] = "ModelBenchLab"
        endpoint = BASE_URL if routed else config["endpoint"].rstrip("/")
        response = client.post(
            endpoint + "/chat/completions", headers=headers, json=payload
        )
        check_response(response)
        data = response.json()
        choice = data["choices"][0]
        output = choice["message"]["content"]
        if not isinstance(output, str):
            raise ValueError("Non-text content")
        usage = data.get("usage") or {}
        if not isinstance(usage, dict):
            raise ValueError("Invalid usage")

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

        return {
            "output": output,
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
            "cost": price(usage.get("cost")) if routed else None,
            "cost_source": "openrouter_usage"
            if routed and price(usage.get("cost")) is not None
            else None,
            "routing": payload.get("provider"),
        }
    except httpx.TimeoutException:
        raise ProviderError(
            "模型請求逾時；上游可能已執行並計費，請手動確認後重跑",
            code="timeout_uncertain",
        )
    except httpx.RequestError:
        raise ProviderError(
            "連線中斷；上游可能已收到請求，請手動確認後重跑",
            code="connection_uncertain",
        )
    except (KeyError, IndexError, ValueError, TypeError, AttributeError):
        raise ProviderError("模型回應格式不符合 chat/completions 文字格式")
    finally:
        if own:
            client.close()
