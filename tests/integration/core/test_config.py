import logging

import pytest
from app.core.config import Settings
from app.core.constants import Environment
from pydantic import ValidationError


def test_settings_log_level_validation() -> None:
    settings_debug = Settings(log_level="debug")
    assert settings_debug.log_level == "DEBUG"
    assert settings_debug.log_level_int == logging.DEBUG

    settings_dev = Settings(log_level=None, app_env=Environment.DEV)
    assert settings_dev.log_level is None
    assert settings_dev.log_level_int == logging.DEBUG

    settings_test = Settings(log_level=None, app_env=Environment.TEST)
    assert settings_test.log_level_int == logging.WARNING

    settings_qa = Settings(log_level=None, app_env=Environment.QA)
    assert settings_qa.log_level_int == logging.INFO

    settings_prod = Settings(log_level=None, app_env=Environment.PROD)
    assert settings_prod.log_level_int == logging.INFO

    with pytest.raises(ValidationError, match="Must be one of"):
        Settings(log_level="INVALID")


def test_settings_api_prefix_validation() -> None:
    settings = Settings(api_prefix="/v1")
    assert settings.api_prefix == "/v1"

    settings_root = Settings(api_prefix="/")
    assert settings_root.api_prefix == "/"

    with pytest.raises(ValidationError, match="must not be empty"):
        Settings(api_prefix="")

    with pytest.raises(ValidationError, match="must start with '/'"):
        Settings(api_prefix="v1")

    with pytest.raises(ValidationError, match="must not end with '/'"):
        Settings(api_prefix="/v1/")


def test_settings_request_hardening_validation() -> None:
    settings = Settings(max_request_body_bytes=2048, request_timeout_seconds=15.0)
    assert settings.max_request_body_bytes == 2048
    assert settings.request_timeout_seconds == 15.0

    with pytest.raises(ValidationError, match="greater than 0"):
        Settings(max_request_body_bytes=0)

    with pytest.raises(ValidationError, match="greater than 0"):
        Settings(request_timeout_seconds=0)


def test_settings_db_pool_validation() -> None:
    settings = Settings(db_pool_size=20, db_max_overflow=30, db_pool_recycle_seconds=1800)
    assert settings.db_pool_size == 20
    assert settings.db_max_overflow == 30
    assert settings.db_pool_recycle_seconds == 1800

    # Defaults mirror SQLAlchemy's QueuePool defaults (recycle -1 = disabled), so the
    # knobs are additive — unset behaviour is identical to before they existed.
    defaults = Settings()
    assert defaults.db_pool_size == 5
    assert defaults.db_max_overflow == 10
    assert defaults.db_pool_recycle_seconds == -1

    with pytest.raises(ValidationError, match="greater than or equal to 1"):
        Settings(db_pool_size=0)
    with pytest.raises(ValidationError, match="greater than or equal to 0"):
        Settings(db_max_overflow=-1)
    with pytest.raises(ValidationError, match="greater than or equal to -1"):
        Settings(db_pool_recycle_seconds=-2)


def test_settings_db_timeout_validation() -> None:
    s = Settings(db_statement_timeout_ms=8000, db_lock_timeout_ms=3000, db_pool_timeout_seconds=4.0)
    assert s.db_statement_timeout_ms == 8000
    assert s.db_lock_timeout_ms == 3000
    assert s.db_pool_timeout_seconds == 4.0

    defaults = Settings()
    assert defaults.db_statement_timeout_ms == 10_000
    assert defaults.db_lock_timeout_ms == 5_000
    assert defaults.db_pool_timeout_seconds == 5.0

    with pytest.raises(ValidationError, match="greater than or equal to 0"):
        Settings(db_statement_timeout_ms=-1)
    with pytest.raises(ValidationError, match="greater than 0"):
        Settings(db_pool_timeout_seconds=0)
