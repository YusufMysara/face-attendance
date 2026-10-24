"""One engine (connection pool) for the whole app; one short-lived session per request."""
from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import database_url

engine = create_engine(database_url(), pool_pre_ping=True)  # pre_ping: test a connection before reusing it
SessionLocal = sessionmaker(engine, expire_on_commit=False)  # keep returned objects readable after commit


def get_session() -> Iterator[Session]:
    with SessionLocal() as session:
        yield session
