# pyright: reportPrivateUsage=false
import pytest
from app.core import database
from app.core.config import settings
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool


def test_pool_options_applies_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "db_pool_size", 7)
    monkeypatch.setattr(settings, "db_max_overflow", 3)
    monkeypatch.setattr(settings, "db_pool_recycle_seconds", 900)
    monkeypatch.setattr(settings, "db_pool_timeout_seconds", 4.0)
    monkeypatch.setattr(settings, "db_statement_timeout_ms", 8000)
    monkeypatch.setattr(settings, "db_lock_timeout_ms", 3000)
    assert database._pool_options(None) == {
        "pool_pre_ping": True,
        "pool_size": 7,
        "max_overflow": 3,
        "pool_recycle": 900,
        "pool_timeout": 4.0,
        "connect_args": {"server_settings": {"statement_timeout": "8000", "lock_timeout": "3000"}},
    }


def test_pool_options_nullpool_omits_sizing() -> None:
    # A test/NullPool engine takes no sizing args — NullPool does not pool.
    assert database._pool_options(NullPool) == {"poolclass": NullPool}


async def test_connect_args_set_statement_timeout_on_a_live_connection() -> None:
    # The NullPool suite never exercises the connect_args branch; prove server_settings
    # actually reach Postgres on a real connection (the prod-only pool path).
    url = database.get_engine().url.render_as_string(hide_password=False)
    engine = create_async_engine(url, connect_args={"server_settings": {"statement_timeout": "250"}})
    try:
        async with engine.connect() as conn:
            timeout = await conn.scalar(text("SHOW statement_timeout"))
    finally:
        await engine.dispose()
    assert timeout == "250ms"
