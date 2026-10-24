"""Test setup. Tests run against their own database and never touch the development one."""
import os

# This must happen BEFORE any app module is imported: app.db.session builds its engine at import time.
TEST_DB = "attendance_test"
os.environ["POSTGRES_DB"] = TEST_DB

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text

from app.db.session import SessionLocal
from app.db.session import engine as db_engine

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session", autouse=True)
def database():
    """A fresh test database, built by the real migrations (so the migrations are tested too)."""
    assert db_engine.url.database == TEST_DB, "tests must never run against the development database"
    admin = create_engine(db_engine.url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as connection:
        connection.execute(text(f"DROP DATABASE IF EXISTS {TEST_DB} WITH (FORCE)"))
        connection.execute(text(f"CREATE DATABASE {TEST_DB}"))
    admin.dispose()
    command.upgrade(Config(str(ROOT / "alembic.ini")), "head")
    yield
    db_engine.dispose()


@pytest.fixture(autouse=True)
def clean_tables(database):
    """Empty every table after each test, so no test depends on another."""
    yield
    with db_engine.begin() as connection:
        connection.execute(text("TRUNCATE employees RESTART IDENTITY CASCADE"))  # cascades to the other two tables


@pytest.fixture
def session():
    with SessionLocal() as db_session:
        yield db_session
