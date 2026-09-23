import os
from datetime import datetime, timezone
from sqlalchemy import create_engine, String, Text, JSON, ForeignKey, event
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

def now():
    return datetime.now(timezone.utc).isoformat()

DATABASE_URL = os.getenv('DATABASE_URL', 'sqlite:///./modelbench.db')
engine = create_engine(DATABASE_URL, connect_args={'check_same_thread': False, 'timeout': 30} if DATABASE_URL.startswith('sqlite') else {}, pool_pre_ping=True)
if DATABASE_URL.startswith('sqlite'):
    @event.listens_for(engine, 'connect')
    def sqlite_settings(conn, _):
        conn.execute('PRAGMA journal_mode=WAL')
        conn.execute('PRAGMA foreign_keys=ON')

Session = sessionmaker(engine, expire_on_commit=False)
class Base(DeclarativeBase):
    pass

class Model(Base):
    __tablename__ = 'model_configs'
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    provider: Mapped[str] = mapped_column(String(30))
    endpoint: Mapped[str] = mapped_column(Text, default='')
    model: Mapped[str] = mapped_column(String(200))
    secret: Mapped[str] = mapped_column(Text, default='')
    created_at: Mapped[str] = mapped_column(String(40), default=now)

class Dataset(Base):
    __tablename__ = 'dataset_versions'
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    cases: Mapped[list] = mapped_column(JSON)
    created_at: Mapped[str] = mapped_column(String(40), default=now)

class Prompt(Base):
    __tablename__ = 'prompt_versions'
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(String(40), default=now)

class Run(Base):
    __tablename__ = 'runs'
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(30), default='queued')
    snapshot: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[str] = mapped_column(String(40), default=now)
    finished_at: Mapped[str | None] = mapped_column(String(40), nullable=True)

class Item(Base):
    __tablename__ = 'run_items'
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey('runs.id'), index=True)
    model_id: Mapped[str] = mapped_column(String(36))
    case_index: Mapped[int]
    repeat_index: Mapped[int]
    status: Mapped[str] = mapped_column(String(30), default='queued', index=True)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    attempts: Mapped[list] = mapped_column(JSON, default=list)
    started_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    finished_at: Mapped[str | None] = mapped_column(String(40), nullable=True)

class Review(Base):
    __tablename__ = 'human_reviews'
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    item_id: Mapped[str] = mapped_column(ForeignKey('run_items.id'), index=True)
    score: Mapped[int]
    note: Mapped[str] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(String(40), default=now)

def init_db():
    Base.metadata.create_all(engine)
