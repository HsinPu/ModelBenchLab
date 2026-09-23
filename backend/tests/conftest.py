import os
import tempfile
from pathlib import Path
from cryptography.fernet import Fernet

TEST_DIR = tempfile.TemporaryDirectory()
os.environ["DATABASE_URL"] = "sqlite:///" + str(Path(TEST_DIR.name) / "test.db")
os.environ["APP_ENCRYPTION_KEY"] = Fernet.generate_key().decode()
os.environ["SEED_DEMO"] = "0"
os.environ["TASK_MODE"] = "local"
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.db import Base, engine


@pytest.fixture
def client():
    Base.metadata.drop_all(engine)
    with engine.begin() as connection:
        connection.exec_driver_sql("DROP TABLE IF EXISTS alembic_version")
    with TestClient(app) as client:
        yield client
    engine.dispose()
