from collections.abc import Generator
from contextlib import contextmanager

from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.core.config import settings

# StaticPool shares one in-memory DB across sessions in the process (Phase 1 SQLite-only).
engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)


def init_schema() -> None:
    SQLModel.metadata.create_all(engine)


@contextmanager
def session_factory() -> Generator[Session]:
    with Session(engine) as session:
        yield session
