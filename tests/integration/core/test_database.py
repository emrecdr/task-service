# pyright: reportPrivateUsage=false
import pytest
from app.core import database
from app.core.config import settings
from sqlalchemy.pool import NullPool


def test_pool_options_applies_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "db_pool_size", 7)
    monkeypatch.setattr(settings, "db_max_overflow", 3)
    monkeypatch.setattr(settings, "db_pool_recycle_seconds", 900)
    assert database._pool_options(None) == {
        "pool_pre_ping": True,
        "pool_size": 7,
        "max_overflow": 3,
        "pool_recycle": 900,
    }


def test_pool_options_nullpool_omits_sizing() -> None:
    # A test/NullPool engine takes no sizing args — NullPool does not pool.
    assert database._pool_options(NullPool) == {"poolclass": NullPool}
