import os
from datetime import datetime, timezone
from sqlalchemy import (
    create_engine,
    String,
    Text,
    JSON,
    ForeignKey,
    UniqueConstraint,
    event,
    inspect,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker


def now():
    return datetime.now(timezone.utc).isoformat()


DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./modelbench.db")
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False, "timeout": 30}
    if DATABASE_URL.startswith("sqlite")
    else {},
    pool_pre_ping=True,
)
if DATABASE_URL.startswith("sqlite"):

    @event.listens_for(engine, "connect")
    def sqlite_settings(conn, _):
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")


Session = sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class Model(Base):
    __tablename__ = "model_configs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    provider: Mapped[str] = mapped_column(String(30))
    endpoint: Mapped[str] = mapped_column(Text, default="")
    model: Mapped[str] = mapped_column(String(200))
    secret: Mapped[str] = mapped_column(Text, default="")
    connection_id: Mapped[str | None] = mapped_column(
        ForeignKey("provider_connections.id"), nullable=True
    )
    enabled: Mapped[bool] = mapped_column(default=True)
    routing: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[str] = mapped_column(String(40), default=now)


class ProviderConnection(Base):
    __tablename__ = "provider_connections"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    provider: Mapped[str] = mapped_column(String(30))
    endpoint: Mapped[str] = mapped_column(Text)
    secret: Mapped[str] = mapped_column(Text, default="")
    enabled: Mapped[bool] = mapped_column(default=True)
    status: Mapped[str] = mapped_column(String(30), default="unverified")
    credential_version: Mapped[int] = mapped_column(default=1)
    usage: Mapped[dict] = mapped_column(JSON, default=dict)
    last_checked_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    last_synced_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[str] = mapped_column(String(40), default=now)


class CatalogModel(Base):
    __tablename__ = "model_catalog"
    __table_args__ = (
        UniqueConstraint(
            "connection_id", "model_id", name="uq_catalog_connection_model"
        ),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    connection_id: Mapped[str] = mapped_column(
        ForeignKey("provider_connections.id"), index=True
    )
    model_id: Mapped[str] = mapped_column(String(200))
    name: Mapped[str] = mapped_column(String(300))
    author: Mapped[str] = mapped_column(String(100))
    details: Mapped[dict] = mapped_column(JSON)
    available: Mapped[bool] = mapped_column(default=True)
    synced_at: Mapped[str] = mapped_column(String(40), default=now)


class Dataset(Base):
    __tablename__ = "dataset_versions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    cases: Mapped[list] = mapped_column(JSON)
    created_at: Mapped[str] = mapped_column(String(40), default=now)


class Prompt(Base):
    __tablename__ = "prompt_versions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(String(40), default=now)


class Run(Base):
    __tablename__ = "runs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(30), default="queued")
    snapshot: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[str] = mapped_column(String(40), default=now)
    finished_at: Mapped[str | None] = mapped_column(String(40), nullable=True)


class Item(Base):
    __tablename__ = "run_items"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"), index=True)
    model_id: Mapped[str] = mapped_column(String(36))
    case_index: Mapped[int]
    repeat_index: Mapped[int]
    status: Mapped[str] = mapped_column(String(30), default="queued", index=True)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    attempts: Mapped[list] = mapped_column(JSON, default=list)
    started_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    finished_at: Mapped[str | None] = mapped_column(String(40), nullable=True)


class Review(Base):
    __tablename__ = "human_reviews"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    item_id: Mapped[str] = mapped_column(ForeignKey("run_items.id"), index=True)
    score: Mapped[int]
    note: Mapped[str] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(String(40), default=now)


def init_db():
    """Serialize startup migrations; SQLite upgrades get a consistent local backup."""
    from pathlib import Path
    from alembic import command
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    root = Path(__file__).resolve().parent.parent
    config = Config(str(root / "alembic.ini"))
    head = ScriptDirectory.from_config(config).get_current_head()
    with engine.connect() as connection:
        if engine.dialect.name == "sqlite":
            connection.exec_driver_sql("BEGIN IMMEDIATE")
        else:
            connection.begin()
            connection.execute(text("SELECT pg_advisory_xact_lock(721543829)"))
        try:
            tables = inspect(connection).get_table_names()
            revision = (
                connection.execute(
                    text("SELECT version_num FROM alembic_version")
                ).scalar()
                if "alembic_version" in tables
                else None
            )
            if revision == head:
                connection.commit()
                return
            if (
                "model_configs" in tables
                and engine.dialect.name == "sqlite"
                and engine.url.database not in (None, ":memory:")
            ):
                import sqlite3

                path = Path(engine.url.database).resolve()
                backup = path.with_name(
                    path.name
                    + ".pre-v02-"
                    + datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
                    + ".bak"
                )
                # A separate read connection includes committed WAL contents.
                with (
                    sqlite3.connect(str(path)) as source,
                    sqlite3.connect(str(backup)) as target,
                ):
                    source.backup(target)
            config.attributes["connection"] = connection
            command.upgrade(config, "head")
            connection.commit()
        except Exception:
            connection.rollback()
            raise
