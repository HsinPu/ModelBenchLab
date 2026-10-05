from typing import Literal
from pydantic import BaseModel, Field, model_validator
from urllib.parse import urlsplit
from jsonschema.validators import validator_for

ReasoningEffort = Literal['low', 'medium', 'high', 'xhigh', 'max', 'ultra']
DEFAULT_NETWORK_TIMEOUT = 600
MAX_NETWORK_TIMEOUT = 600


class TrialInput(BaseModel):
    timeout: int = Field(default=DEFAULT_NETWORK_TIMEOUT, ge=5, le=MAX_NETWORK_TIMEOUT)

class ModelInput(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    provider: Literal['openai-compatible', 'demo'] = 'openai-compatible'
    endpoint: str = Field(default='', max_length=2000)
    model: str = Field(min_length=1, max_length=200)
    api_key: str = Field(default='', max_length=4000)
    reasoning_effort: ReasoningEffort | None = None
    max_output_tokens: int = Field(default=128000, ge=1, le=131072)
    @model_validator(mode='after')
    def endpoint_valid(self):
        if self.provider == 'openai-compatible':
            url = urlsplit(self.endpoint)
            if url.scheme not in ('http', 'https') or not url.hostname or url.username or url.password or url.query or url.fragment:
                raise ValueError('請輸入 http(s) API base URL，不可包含帳密或查詢參數')
        return self

class Message(BaseModel):
    role: Literal['user', 'assistant']
    content: str = Field(min_length=1, max_length=20000)

class Rule(BaseModel):
    kind: Literal['manual', 'exact', 'contains', 'choice', 'json_schema'] = 'manual'
    expected: str = Field(default='', max_length=20000)
    schema_: dict = Field(default_factory=dict, alias='schema')
    @model_validator(mode='after')
    def valid_rule(self):
        if self.kind in ('exact', 'contains', 'choice') and not self.expected.strip():
            raise ValueError('比對規則必須提供 expected')
        if self.kind == 'choice' and self.expected.strip().upper() not in ('A', 'B', 'C', 'D'):
            raise ValueError('選擇題答案必須是 A、B、C 或 D')
        if self.kind == 'json_schema':
            # Remote references would cause uncontrolled network fetches.
            def walk(v):
                if isinstance(v, dict):
                    for k, value in v.items():
                        if k in ('$ref', '$dynamicRef') and (not isinstance(value, str) or not value.startswith('#')):
                            raise ValueError('Schema 只允許本地參照')
                        walk(value)
                elif isinstance(v, list):
                    for value in v: walk(value)
            walk(self.schema_)
            try:
                validator_for(self.schema_).check_schema(self.schema_)
            except Exception:
                raise ValueError('JSON Schema 格式錯誤')
        return self

class Case(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    messages: list[Message] = Field(min_length=1, max_length=30)
    rule: Rule = Field(default_factory=Rule)
    tags: list[str] = Field(default_factory=list, max_length=20)
    source: dict | None = None

class DatasetInput(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    cases: list[Case] = Field(min_length=1, max_length=1000)

class DatasetBundleInput(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    cases: list[Case] = Field(min_length=1001, max_length=30000)

class PromptInput(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    text: str = Field(max_length=20000)

class RunInput(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    dataset_id: str
    model_ids: list[str] = Field(min_length=1, max_length=10)
    prompt_id: str
    repeats: int = Field(default=1, ge=1, le=5)
    temperature: float = Field(default=0, ge=0, le=2)
    max_tokens: int | None = Field(default=None, ge=1, le=131072)
    timeout: int = Field(default=DEFAULT_NETWORK_TIMEOUT, ge=5, le=MAX_NETWORK_TIMEOUT)
    @model_validator(mode='after')
    def unique_models(self):
        if len(set(self.model_ids)) != len(self.model_ids):
            raise ValueError('模型不可重複')
        return self

class RunBatchInput(RunInput):
    dataset_id: str | None = None
    bundle_id: str

class ReviewInput(BaseModel):
    score: int = Field(ge=1, le=5)
    note: str = Field(default='', max_length=4000)
