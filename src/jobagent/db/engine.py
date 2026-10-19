from __future__ import annotations
import sqlalchemy as sa
from .tables import metadata


def normalize_url(url: str) -> str:
    """Accept the URL forms hosting providers hand out and map them to the psycopg3 driver."""
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://"):]
    return url


def make_engine(url: str = "sqlite:///jobagent.db") -> sa.Engine:
    url = normalize_url(url)
    if url.startswith("sqlite"):
        engine = sa.create_engine(url, future=True, connect_args={"check_same_thread": False, "timeout": 30})

        @sa.event.listens_for(engine, "connect")
        def _fk(dbapi_conn, _):  # noqa: ANN001
            dbapi_conn.execute("PRAGMA foreign_keys=ON")
            dbapi_conn.execute("PRAGMA journal_mode=WAL")
        return engine
    return sa.create_engine(url, future=True, pool_pre_ping=True, pool_size=5, max_overflow=5)


def init_db(engine: sa.Engine) -> None:
    metadata.create_all(engine)
