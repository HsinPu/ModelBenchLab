from datetime import datetime, timezone, timedelta
from decimal import Decimal
from uuid import uuid4
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field, ConfigDict, model_validator
from sqlalchemy import select, update
from .db import Session, Model, ProviderConnection, CatalogModel, Item, now
from .security import encrypt, decrypt
from . import openrouter
from .provider_types import PROVIDER_TYPES, connection_endpoint
from .schemas import ReasoningEffort

router = APIRouter(prefix="/api")


class ConnectionInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    provider: str = "openrouter"
    name: str = Field(min_length=1, max_length=100)
    endpoint: str = Field(default="", max_length=2000)
    api_key: str = Field(default="", max_length=4000)

    @model_validator(mode="after")
    def valid_provider(self):
        provider = PROVIDER_TYPES.get(self.provider)
        if provider is None:
            raise ValueError("不支援的服務類型")
        if provider.requires_api_key and not self.api_key:
            raise ValueError("此服務需要 API Key")
        self.endpoint = connection_endpoint(provider, self.endpoint)
        return self


class ConnectionUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str | None = Field(default=None, min_length=1, max_length=100)
    api_key: str | None = Field(default=None, min_length=1, max_length=4000)
    endpoint: str | None = Field(default=None, max_length=2000)
    enabled: bool | None = None


class ImportModels(BaseModel):
    model_ids: list[str] = Field(min_length=1, max_length=100)
    reasoning_effort: ReasoningEffort | None = None
    max_output_tokens: int = Field(default=32768, ge=1, le=131072)


class ModelUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool | None = None
    reasoning_effort: ReasoningEffort | None = None
    max_output_tokens: int | None = Field(default=None, ge=1, le=131072)

    @model_validator(mode="after")
    def has_change(self):
        if (
            not self.model_fields_set
            or "enabled" in self.model_fields_set and self.enabled is None
            or "max_output_tokens" in self.model_fields_set and self.max_output_tokens is None
        ):
            raise ValueError("請指定要更新的模型設定")
        return self


class ManualModelInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=100)
    model_id: str = Field(min_length=1, max_length=200)
    reasoning_effort: ReasoningEffort | None = None
    max_output_tokens: int = Field(default=32768, ge=1, le=131072)


def required(db, cls, identifier):
    row = db.get(cls, identifier)
    if row is None:
        raise HTTPException(404, "找不到指定資料")
    return row


def public_connection(row):
    return {
        **{
            k: getattr(row, k)
            for k in (
                "id",
                "name",
                "provider",
                "endpoint",
                "enabled",
                "status",
                "usage",
                "last_checked_at",
                "last_synced_at",
                "error",
                "created_at",
            )
        },
        "has_key": bool(row.secret),
    }


def require_ready(connection, verified=True):
    if not connection.enabled:
        raise HTTPException(409, "廠商連線已停用，請先啟用")
    provider = PROVIDER_TYPES.get(connection.provider)
    if (
        verified
        and provider
        and provider.verification == "metadata"
        and connection.status != "verified"
    ):
        raise HTTPException(409, "請先驗證廠商連線")


def catalog_entry(db, model):
    return db.scalar(
        select(CatalogModel).where(
            CatalogModel.connection_id == model.connection_id,
            CatalogModel.model_id == model.model,
        )
    )


def public_model(row, db):
    connection = (
        db.get(ProviderConnection, row.connection_id) if row.connection_id else None
    )
    provider = PROVIDER_TYPES.get(row.provider)
    catalog = catalog_entry(db, row) if provider and provider.supports_catalog else None
    available = True
    reason = ""
    if provider and provider.supports_catalog:
        if not connection or connection.status != "verified":
            available, reason = False, "請先驗證廠商連線"
        elif not catalog or not catalog.available:
            available, reason = False, "模型已下架或尚未同步"
        elif not catalog.details.get("text_compatible"):
            available, reason = False, "目前題庫只支援文字輸入與文字回答"
    if connection is not None and not connection.enabled:
        available, reason = False, "廠商連線已停用"
    if not row.enabled:
        available, reason = False, "模型已停用"
    return {
        "id": row.id,
        "name": row.name,
        "provider": row.provider,
        "endpoint": connection.endpoint if connection else row.endpoint,
        "model": row.model,
        "has_key": bool(connection.secret if connection else row.secret),
        "connection_id": row.connection_id,
        "connection_name": connection.name if connection else None,
        "credential_version": connection.credential_version if connection else None,
        "enabled": row.enabled,
        "available": available,
        "unavailable_reason": reason,
        "routing": row.routing or {},
        "reasoning_effort": row.reasoning_effort,
        "max_output_tokens": row.max_output_tokens,
        "catalog": catalog.details if catalog else None,
        "catalog_synced_at": catalog.synced_at if catalog else None,
    }


def validate_model(db, row, settings):
    if row.deleted_at is not None:
        raise HTTPException(409, "模型已從管理清單移除，不能建立新測試")
    result = public_model(row, db)
    if not result["available"]:
        raise HTTPException(409, row.name + "：" + result["unavailable_reason"])
    provider = PROVIDER_TYPES.get(row.provider)
    if provider and provider.supports_catalog:
        details = result["catalog"]
        limit = details.get("max_completion_tokens")
        requested = settings.get("max_tokens") or row.max_output_tokens
        if (
            "max_tokens" in details.get("supported_parameters", [])
            and isinstance(limit, int)
            and requested > limit
        ):
            raise HTTPException(422, row.name + f" 的輸出上限為 {limit} tokens")
    return result


def execution_key(db, config, model):
    # Refresh before each attempt so disabled connections/rotated keys are respected.
    db.refresh(model)
    if not model.enabled:
        raise openrouter.ProviderError("模型已停用", code="model_disabled")
    cid = config.get("connection_id") or model.connection_id
    if not cid:
        return decrypt(model.secret), None
    connection = db.get(ProviderConnection, cid, populate_existing=True)
    if not connection or not connection.enabled:
        raise openrouter.ProviderError(
            "廠商連線已停用，尚未發出新請求", code="connection_disabled"
        )
    provider = PROVIDER_TYPES.get(connection.provider)
    if (
        provider
        and provider.verification == "metadata"
        and connection.status != "verified"
    ):
        raise openrouter.ProviderError(
            "廠商金鑰尚未驗證，請重新驗證連線", code="connection_unverified"
        )
    return decrypt(connection.secret), connection.credential_version


@router.get("/connections")
def list_connections():
    with Session() as db:
        return [
            public_connection(c)
            for c in db.scalars(
                select(ProviderConnection).order_by(ProviderConnection.created_at)
            )
        ]


@router.get("/providers")
def list_provider_types():
    return [provider.public() for provider in PROVIDER_TYPES.values()]


@router.post("/connections", status_code=201)
def create_connection(body: ConnectionInput):
    with Session() as db:
        row = ProviderConnection(
            id=str(uuid4()),
            name=body.name,
            provider=body.provider,
            endpoint=body.endpoint,
            secret=encrypt(body.api_key),
            status="unverified"
            if PROVIDER_TYPES[body.provider].verification == "metadata"
            else "not_applicable",
        )
        db.add(row)
        db.commit()
        return public_connection(row)


@router.patch("/connections/{identifier}")
def update_connection(identifier: str, body: ConnectionUpdate):
    with Session() as db:
        db.execute(
            update(ProviderConnection)
            .where(ProviderConnection.id == identifier)
            .values(id=identifier)
        )
        row = required(db, ProviderConnection, identifier)
        provider = PROVIDER_TYPES.get(row.provider)
        if body.name is not None:
            row.name = body.name
        if body.endpoint is not None:
            if provider is None:
                raise HTTPException(422, "此服務類型尚不支援修改 API 位址")
            try:
                row.endpoint = connection_endpoint(provider, body.endpoint)
            except ValueError as error:
                raise HTTPException(422, str(error)) from error
        if body.enabled is not None:
            row.enabled = body.enabled
        if body.api_key is not None:
            row.secret = encrypt(body.api_key)
            row.credential_version += 1
            row.status = (
                "unverified"
                if provider and provider.verification == "metadata"
                else "not_applicable"
            )
            row.last_checked_at = None
            row.usage = {}
            row.error = ""
        db.commit()
        return public_connection(row)


@router.post("/connections/{identifier}/verify")
def verify_connection(identifier: str):
    with Session() as db:
        row = required(db, ProviderConnection, identifier)
        require_ready(row, verified=False)
        provider = PROVIDER_TYPES.get(row.provider)
        if provider is None or provider.verify_key is None:
            raise HTTPException(422, "此服務透過模型試跑檢查，不提供免推論的金鑰驗證")
        version = row.credential_version
        key = decrypt(row.secret)
    error = None
    try:
        usage = provider.verify_key(key)
    except openrouter.ProviderError as e:
        error = e
        usage = {}
    with Session() as db:
        db.execute(
            update(ProviderConnection)
            .where(ProviderConnection.id == identifier)
            .values(id=identifier)
        )
        row = required(db, ProviderConnection, identifier)
        if row.credential_version != version or not row.enabled:
            raise HTTPException(409, "連線已更新，請重新驗證")
        row.status = (
            ("invalid" if error.code in ("invalid_key", "forbidden") else "error")
            if error
            else "verified"
        )
        row.error = str(error) if error else ""
        row.usage = usage
        row.last_checked_at = now()
        db.commit()
        if error:
            raise HTTPException(502, str(error))
        return public_connection(row)


@router.post("/connections/{identifier}/sync")
def sync_catalog(identifier: str, force: bool = False):
    with Session() as db:
        row = required(db, ProviderConnection, identifier)
        require_ready(row)
        provider = PROVIDER_TYPES.get(row.provider)
        if provider is None or provider.list_models is None:
            raise HTTPException(422, "此連線不支援模型目錄")
        if (
            not force
            and row.last_synced_at
            and datetime.fromisoformat(row.last_synced_at)
            > datetime.now(timezone.utc) - timedelta(minutes=15)
        ):
            return {"cached": True, "synced_at": row.last_synced_at}
        version, key = row.credential_version, decrypt(row.secret)
    try:
        models = provider.list_models(key)
    except openrouter.ProviderError as e:
        with Session() as db:
            db.execute(
                update(ProviderConnection)
                .where(ProviderConnection.id == identifier)
                .values(id=identifier)
            )
            row = required(db, ProviderConnection, identifier)
            if row.credential_version == version:
                row.error = str(e)
                if e.code in ("invalid_key", "forbidden"):
                    row.status = "invalid"
                db.commit()
        raise HTTPException(502, str(e))
    with Session() as db:
        # Serialize same-connection sync/import on PostgreSQL; SQLite writer lock
        # is acquired by this no-op update before reading catalog rows.
        db.execute(
            update(ProviderConnection)
            .where(ProviderConnection.id == identifier)
            .values(id=identifier)
        )
        row = required(db, ProviderConnection, identifier)
        if row.credential_version != version or not row.enabled:
            raise HTTPException(409, "連線已更新，請重新同步")
        current = {
            m.model_id: m
            for m in db.scalars(
                select(CatalogModel).where(CatalogModel.connection_id == identifier)
            )
        }
        stamp = now()
        for m in current.values():
            m.available = False
        for model in models:
            existing = current.get(model["model_id"])
            if existing:
                existing.name, existing.author, existing.details = (
                    model["name"],
                    model["author"],
                    model["details"],
                )
                existing.available, existing.synced_at = True, stamp
            else:
                db.add(
                    CatalogModel(
                        id=str(uuid4()),
                        connection_id=identifier,
                        available=True,
                        synced_at=stamp,
                        **model,
                    )
                )
        row.last_synced_at, row.error = stamp, ""
        db.commit()
        return {"cached": False, "count": len(models), "synced_at": stamp}


@router.get("/connections/{identifier}/catalog")
def get_catalog(
    identifier: str,
    q: str = "",
    author: str = "",
    free_only: bool = False,
    text_only: bool = True,
    unadded_only: bool = False,
    selectable_only: bool = False,
    capability: str = "",
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
):
    with Session() as db:
        connection = required(db, ProviderConnection, identifier)
        provider = PROVIDER_TYPES.get(connection.provider)
        if provider is None or not provider.supports_catalog:
            raise HTTPException(422, "此連線不支援模型目錄")
        rows = db.scalars(
            select(CatalogModel)
            .where(
                CatalogModel.connection_id == identifier,
                CatalogModel.available.is_(True),
            )
            .order_by(CatalogModel.name)
        ).all()
        added = set(
            db.scalars(
                select(Model.model).where(
                    Model.connection_id == identifier, Model.deleted_at.is_(None)
                )
            )
        )
        authors = sorted({r.author for r in rows})
        entries = []
        for row in rows:
            details = row.details
            if q.casefold() not in (row.name + " " + row.model_id).casefold():
                continue
            if author and row.author != author:
                continue
            if text_only and not details["text_compatible"]:
                continue
            selectable = details["text_compatible"]
            if selectable_only and not selectable:
                continue
            if unadded_only and row.model_id in added:
                continue
            prices = details["pricing"]
            free = (
                details["fixed_model"]
                and prices.get("prompt") is not None
                and prices.get("completion") is not None
                and all(Decimal(prices[k]) == 0 for k in ("prompt", "completion"))
                and all(
                    prices.get(k) is None or Decimal(prices[k]) == 0
                    for k in ("request", "image")
                )
            )
            if free_only and not free:
                continue
            if capability and capability not in details["supported_parameters"]:
                continue
            entries.append(
                {
                    "id": row.id,
                    "model_id": row.model_id,
                    "name": row.name,
                    "author": row.author,
                    "details": details,
                    "added": row.model_id in added,
                    "free": free,
                    "selectable": selectable,
                    "synced_at": row.synced_at,
                }
            )
        return {
            "items": entries[offset : offset + limit],
            "total": len(entries),
            "authors": authors,
            "synced_at": connection.last_synced_at,
            "error": connection.error,
        }


@router.post("/connections/{identifier}/models", status_code=201)
def import_models(identifier: str, body: ImportModels):
    with Session() as db:
        db.execute(
            update(ProviderConnection)
            .where(ProviderConnection.id == identifier)
            .values(id=identifier)
        )
        row = required(db, ProviderConnection, identifier)
        require_ready(row)
        provider = PROVIDER_TYPES.get(row.provider)
        if provider is None or not provider.supports_catalog:
            raise HTTPException(422, "此連線不支援模型目錄")
        requested = list(dict.fromkeys(body.model_ids))
        entries = list(
            db.scalars(
                select(CatalogModel).where(
                    CatalogModel.connection_id == identifier,
                    CatalogModel.model_id.in_(requested),
                )
            )
        )
        if len(entries) != len(requested) or any(
            not c.available
            or not c.details["text_compatible"]
            for c in entries
        ):
            raise HTTPException(
                422,
                "包含已下架或無法回答文字題目的模型，請重新同步並選擇",
            )
        existing = set(
            db.scalars(
                select(Model.model).where(
                    Model.connection_id == identifier, Model.deleted_at.is_(None)
                )
            )
        )
        created = []
        for entry in entries:
            if entry.model_id in existing:
                continue
            model = Model(
                id=str(uuid4()),
                name=entry.name[:100],
                provider=row.provider,
                endpoint=row.endpoint,
                model=entry.model_id,
                secret="",
                connection_id=identifier,
                routing=(
                    dict(openrouter.DEFAULT_ROUTING)
                    if row.provider == "openrouter" and entry.details["fixed_model"]
                    else {}
                ),
                reasoning_effort=body.reasoning_effort,
                max_output_tokens=body.max_output_tokens,
            )
            db.add(model)
            created.append(model.id)
        db.commit()
        return {
            "created": len(created),
            "skipped": len(requested) - len(created),
            "ids": created,
        }


@router.post("/connections/{identifier}/models/manual", status_code=201)
def add_manual_model(identifier: str, body: ManualModelInput):
    with Session() as db:
        db.execute(
            update(ProviderConnection)
            .where(ProviderConnection.id == identifier)
            .values(id=identifier)
        )
        connection = required(db, ProviderConnection, identifier)
        require_ready(connection, verified=False)
        provider = PROVIDER_TYPES.get(connection.provider)
        if provider is None or provider.supports_catalog:
            raise HTTPException(422, "此服務請從模型目錄加入模型")
        existing = db.scalar(
            select(Model).where(
                Model.connection_id == identifier,
                Model.model == body.model_id,
                Model.deleted_at.is_(None),
            )
        )
        if existing:
            return {"created": False, "id": existing.id}
        model = Model(
            id=str(uuid4()),
            name=body.name,
            provider=connection.provider,
            endpoint=connection.endpoint,
            model=body.model_id,
            secret="",
            connection_id=identifier,
            routing={},
            reasoning_effort=body.reasoning_effort,
            max_output_tokens=body.max_output_tokens,
        )
        db.add(model)
        db.commit()
        return {"created": True, "id": model.id}


@router.patch("/models/{identifier}")
def update_model(identifier: str, body: ModelUpdate):
    with Session() as db:
        row = required(db, Model, identifier)
        if row.deleted_at is not None:
            raise HTTPException(404, "找不到指定模型")
        if "enabled" in body.model_fields_set:
            row.enabled = body.enabled
        if "reasoning_effort" in body.model_fields_set:
            row.reasoning_effort = body.reasoning_effort
        if "max_output_tokens" in body.model_fields_set:
            row.max_output_tokens = body.max_output_tokens
        db.commit()
        return public_model(row, db)


@router.delete("/models/{identifier}")
def delete_model(identifier: str):
    with Session() as db:
        row = required(db, Model, identifier)
        if row.deleted_at is not None:
            return {"deleted": True}
        pending = db.scalar(
            select(Item.id)
            .where(Item.model_id == identifier, Item.status.in_(("queued", "running")))
            .limit(1)
        )
        if pending:
            raise HTTPException(409, "模型有排隊或執行中的測試；請等待完成或先取消測試")
        row.enabled = False
        row.deleted_at = now()
        db.commit()
        return {"deleted": True}
