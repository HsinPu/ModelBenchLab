import os
from pathlib import Path
import subprocess
import sys
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from app.security import encrypt, decrypt

ROOT = Path(__file__).resolve().parents[1]


def test_legacy_upgrade_preserves_ids_keys_and_history(tmp_path):
    path = tmp_path / "legacy.db"
    engine = sa.create_engine("sqlite:///" + str(path))
    cfg = Config(str(ROOT / "alembic.ini"))
    with engine.begin() as connection:
        cfg.attributes["connection"] = connection
        command.upgrade(cfg, "0001")
        meta = sa.MetaData()
        meta.reflect(connection)
        for index in range(2):
            connection.execute(
                meta.tables["model_configs"]
                .insert()
                .values(
                    id=f"m{index}",
                    name="same endpoint",
                    provider="openai-compatible",
                    endpoint="https://example.test/v1",
                    model="model",
                    secret=encrypt(f"test-{index}"),
                    created_at="2026-01-01",
                )
            )
        connection.execute(
            meta.tables["runs"]
            .insert()
            .values(
                id="run-old",
                name="history",
                status="completed",
                snapshot={"models": [{"id": "m0"}], "keep": "unchanged"},
                created_at="2026-01-01",
            )
        )
        connection.execute(
            meta.tables["run_items"]
            .insert()
            .values(
                id="item-old",
                run_id="run-old",
                model_id="m0",
                case_index=0,
                repeat_index=0,
                status="completed",
                result={"output": "keep"},
                attempts=[],
            )
        )
        connection.execute(
            meta.tables["human_reviews"]
            .insert()
            .values(
                id="review-old",
                item_id="item-old",
                score=4,
                note="keep review",
                created_at="2026-01-01",
            )
        )
        connection.exec_driver_sql(
            "DROP TABLE alembic_version"
        )  # real v0.1 has no migration stamp
    env = {**os.environ, "DATABASE_URL": "sqlite:///" + str(path)}
    for _ in range(2):
        result = subprocess.run(
            [sys.executable, "-c", "from app.db import init_db; init_db()"],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr
    with engine.connect() as connection:
        meta = sa.MetaData()
        meta.reflect(connection)
        models = list(
            connection.execute(sa.select(meta.tables["model_configs"])).mappings()
        )
        connections = list(
            connection.execute(
                sa.select(meta.tables["provider_connections"])
            ).mappings()
        )
        assert {m["id"] for m in models} == {"m0", "m1"} and all(
            not m["secret"] for m in models
        )
        assert len(connections) == 2 and {
            decrypt(c["secret"]) for c in connections
        } == {"test-0", "test-1"}
        assert len({m["connection_id"] for m in models}) == 2
        assert (
            connection.execute(sa.select(meta.tables["runs"].c.snapshot)).scalar()[
                "keep"
            ]
            == "unchanged"
        )
        assert connection.execute(
            sa.select(meta.tables["run_items"].c.result)
        ).scalar() == {"output": "keep"}
        assert (
            connection.execute(sa.select(meta.tables["human_reviews"].c.note)).scalar()
            == "keep review"
        )
        assert connection.exec_driver_sql("PRAGMA foreign_key_check").all() == []
        assert (
            connection.exec_driver_sql(
                "SELECT version_num FROM alembic_version"
            ).scalar()
            == "0002"
        )
    backups = list(tmp_path.glob("*.bak"))
    assert len(backups) == 1
    backup_engine = sa.create_engine("sqlite:///" + str(backups[0]))
    assert "provider_connections" not in sa.inspect(backup_engine).get_table_names()
    backup_engine.dispose()
    engine.dispose()
