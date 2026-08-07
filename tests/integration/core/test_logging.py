import json

import pytest
import structlog
from app.core.config import Settings
from app.core.constants import Environment
from app.core.logging import setup_logging


def test_json_logs_render_machine_parseable_output(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The qa/prod renderer branch. Every other test runs under dev/test, so they all
    exercise ``ConsoleRenderer`` — without this, the one format that actually reaches a
    log aggregator is the one format nothing checks."""
    # Rebind the name ``setup_logging`` reads rather than mutating the shared ``settings``
    # singleton: every module holds that same object, so mutating it would put the whole process
    # in PROD for the duration. ``log_level=None`` selects the APP_ENV matrix default (INFO).
    monkeypatch.setattr("app.core.logging.settings", Settings(app_env=Environment.PROD, log_level=None))
    previous = structlog.get_config()
    try:
        setup_logging()
        structlog.get_logger("json-probe").warning("probe_event", answer=42)
        emitted = capsys.readouterr().out.strip().splitlines()[-1]
    finally:
        # ``setup_logging`` mutates global structlog state; leaving it JSON-configured would
        # change how every later test renders.
        structlog.configure(**previous)

    payload = json.loads(emitted)  # ConsoleRenderer's ANSI-decorated line would not parse
    assert payload["event"] == "probe_event"
    assert payload["level"] == "warning"
    assert payload["answer"] == 42
    assert payload["timestamp"].endswith("Z")  # TimeStamper(fmt="iso", utc=True)
