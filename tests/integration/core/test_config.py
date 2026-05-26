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
