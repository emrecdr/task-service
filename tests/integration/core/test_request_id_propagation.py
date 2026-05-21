from typing import Any

import pytest
import structlog
from app.core import middleware as middleware_mod
from httpx import AsyncClient


class _RecordingLogger:
    """Replaces ``structlog.BoundLogger`` for tests — captures calls and bound contextvars at log time."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def info(self, event: str, **fields: Any) -> None:
        self.calls.append(
            {
                "event": event,
                "request_id_in_context": structlog.contextvars.get_contextvars().get("request_id"),
                **fields,
            }
        )


async def test_request_id_is_generated_when_absent(client: AsyncClient) -> None:
    r = await client.get("/healthz")
    assert r.status_code == 200
    assert "x-request-id" in {k.lower() for k in r.headers}
    assert r.headers["x-request-id"]  # non-empty


async def test_request_id_is_echoed_when_provided(client: AsyncClient) -> None:
    given = "11111111-1111-1111-1111-111111111111"
    r = await client.get("/healthz", headers={"X-Request-ID": given})
    assert r.status_code == 200
    assert r.headers["x-request-id"] == given


async def test_request_id_present_in_error_envelope(client: AsyncClient) -> None:
    given = "22222222-2222-2222-2222-222222222222"
    r = await client.get("/v1/tasks/99999", headers={"X-Request-ID": given})
    assert r.status_code == 404
    err = r.json()["error"]
    assert err["request_id"] == given
    assert r.headers["x-request-id"] == given


async def test_middleware_emits_one_http_request_log_per_request(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Each request must emit exactly one ``http_request`` access log with method/path/status/duration_ms."""
    recorder = _RecordingLogger()
    monkeypatch.setattr(middleware_mod, "logger", recorder)

    given = "33333333-3333-3333-3333-333333333333"
    r = await client.get("/healthz", headers={"X-Request-ID": given})
    assert r.status_code == 200

    http_calls = [c for c in recorder.calls if c["event"] == "http_request"]
    assert len(http_calls) == 1
    call = http_calls[0]
    assert call["method"] == "GET"
    assert call["path"] == "/healthz"
    assert call["status"] == 200
    assert isinstance(call["duration_ms"], float)
    assert call["duration_ms"] >= 0
    # request_id must be bound in contextvars at log-emit time so ``merge_contextvars`` picks it up.
    assert call["request_id_in_context"] == given


async def test_middleware_log_carries_generated_request_id_when_header_absent(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    recorder = _RecordingLogger()
    monkeypatch.setattr(middleware_mod, "logger", recorder)

    r = await client.get("/healthz")
    assert r.status_code == 200
    echoed = r.headers["x-request-id"]

    [call] = [c for c in recorder.calls if c["event"] == "http_request"]
    # The generated request_id in the response header must match the one bound at log-emit time.
    assert call["request_id_in_context"] == echoed


async def test_middleware_log_reflects_error_status(client: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """4xx responses produced by exception handlers must still log via the same access line."""
    recorder = _RecordingLogger()
    monkeypatch.setattr(middleware_mod, "logger", recorder)

    r = await client.get("/v1/tasks/99999")
    assert r.status_code == 404

    [call] = [c for c in recorder.calls if c["event"] == "http_request"]
    assert call["status"] == 404
    assert call["path"] == "/v1/tasks/99999"
