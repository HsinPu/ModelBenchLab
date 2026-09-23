import httpx
import pytest
from app.openrouter import ProviderError, check_response, retry_delay, get_metadata
from app.providers import generate


def test_transient_inflight_budget_respects_retry_after():
    response = httpx.Response(
        402,
        headers={"Retry-After": "7"},
        json={"error": {"metadata": {"limit_source": "openrouter_in_flight_budget"}}},
    )
    with pytest.raises(ProviderError) as e:
        check_response(response)
    assert (
        e.value.retryable
        and e.value.retry_after == 7
        and e.value.code == "in_flight_budget"
    )
    assert retry_delay("NaN") is None and retry_delay("-1") is None


@pytest.mark.parametrize("key", ["fake\nheader", "中文假金鑰"])
def test_bad_key_format_is_sanitized_before_transport(key):
    with pytest.raises(ProviderError) as e:
        get_metadata("/key", key)
    assert e.value.code == "invalid_key_format" and key not in str(e.value)
    with pytest.raises(ProviderError) as e:
        generate(
            {"provider": "openrouter", "model": "maker/test"}, [], {"timeout": 5}, key
        )
    assert e.value.code == "invalid_key_format"


def test_200_with_embedded_error_is_not_a_success():
    with pytest.raises(ProviderError) as e:
        check_response(
            httpx.Response(200, json={"error": {"code": 429, "message": "never-store"}})
        )
    assert e.value.code == "rate_limited" and e.value.retryable
