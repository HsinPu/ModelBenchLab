"""Connection capabilities and provider-specific metadata operations."""

from dataclasses import dataclass
from typing import Callable
from urllib.parse import urlsplit

from . import openrouter


@dataclass(frozen=True)
class ProviderType:
    id: str
    label: str
    description: str
    supports_catalog: bool
    verification: str
    requires_api_key: bool
    fixed_endpoint: str | None = None
    verify_key: Callable | None = None
    list_models: Callable | None = None

    def public(self):
        return {
            "id": self.id,
            "label": self.label,
            "description": self.description,
            "supports_catalog": self.supports_catalog,
            "verification": self.verification,
            "requires_api_key": self.requires_api_key,
            "requires_endpoint": self.fixed_endpoint is None,
            "fixed_endpoint": self.fixed_endpoint,
        }


PROVIDER_TYPES = {
    "openrouter": ProviderType(
        id="openrouter",
        label="OpenRouter",
        description="驗證金鑰後同步模型目錄，從清單批次加入模型。",
        supports_catalog=True,
        verification="metadata",
        requires_api_key=True,
        fixed_endpoint=openrouter.BASE_URL,
        verify_key=lambda key: openrouter.verify_key(key),
        list_models=lambda key: openrouter.list_models(key),
    ),
    "openai-compatible": ProviderType(
        id="openai-compatible",
        label="自訂 OpenAI 相容服務",
        description="填入 API Base URL，手動加入多個模型；可用試跑檢查模型。",
        supports_catalog=False,
        verification="model_trial",
        requires_api_key=False,
    ),
}


def connection_endpoint(provider: ProviderType, supplied: str) -> str:
    if provider.fixed_endpoint:
        if supplied and supplied != provider.fixed_endpoint:
            raise ValueError("此廠商使用固定 API 位址，不可修改")
        return provider.fixed_endpoint
    url = urlsplit(supplied)
    if (
        url.scheme not in ("http", "https")
        or not url.hostname
        or url.username
        or url.password
        or url.query
        or url.fragment
        or any(c.isspace() for c in supplied)
    ):
        raise ValueError("請輸入 http(s) API Base URL，不可包含帳密或查詢參數")
    return supplied.rstrip("/")
