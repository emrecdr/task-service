# pyright: reportPrivateUsage=false
from compression import zstd

import pytest
from app.core.compression import ZstdMiddleware, _client_accepts_zstd
from httpx import AsyncClient
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from tests.conftest import CreateTask

_MIN_SIZE = 500


def _make_app(chunks: list[tuple[bytes, bool]], *, content_encoding: bytes | None = None) -> ASGIApp:
    headers: list[tuple[bytes, bytes]] = [(b"content-type", b"application/json")]
    if content_encoding is not None:
        headers.append((b"content-encoding", content_encoding))

    async def _app(scope: Scope, receive: Receive, send: Send) -> None:
        await send({"type": "http.response.start", "status": 200, "headers": headers})
        for body, more in chunks:
            await send({"type": "http.response.body", "body": body, "more_body": more})

    return _app


async def _drive(app: ZstdMiddleware, *, accept_encoding: str | None) -> list[Message]:
    sent: list[Message] = []

    async def _send(message: Message) -> None:
        sent.append(message)

    async def _receive() -> Message:
        return {"type": "http.request", "body": b"", "more_body": False}

    headers: list[tuple[bytes, bytes]] = []
    if accept_encoding is not None:
        headers.append((b"accept-encoding", accept_encoding.encode()))
    await app({"type": "http", "headers": headers}, _receive, _send)
    return sent


def _headers_of(messages: list[Message]) -> dict[bytes, bytes]:
    start = next(m for m in messages if m["type"] == "http.response.start")
    return dict(start["headers"])


def _body_of(messages: list[Message]) -> bytes:
    return b"".join(m.get("body", b"") for m in messages if m["type"] == "http.response.body")


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        ("zstd", True),
        ("gzip, zstd", True),
        ("zstd;q=0.5", True),
        ("gzip, br", False),
        ("", False),
        ("zstd;q=0", False),  # explicit refusal (RFC 9110 §12.5.3)
        ("zstdx", False),  # must not match on a substring
    ],
)
def test_client_accepts_zstd(header: str, expected: bool) -> None:
    assert _client_accepts_zstd(header) is expected


async def test_middleware_compresses_large_buffered_body() -> None:
    body = b'{"items":["' + b"x" * (_MIN_SIZE * 2) + b'"]}'
    mw = ZstdMiddleware(_make_app([(body, False)]), minimum_size=_MIN_SIZE)
    sent = await _drive(mw, accept_encoding="zstd")
    headers = _headers_of(sent)
    assert headers[b"content-encoding"] == b"zstd"
    assert headers[b"vary"].lower() == b"accept-encoding"
    assert headers[b"content-length"] == str(len(_body_of(sent))).encode()
    assert zstd.decompress(_body_of(sent)) == body


async def test_middleware_skips_body_below_threshold() -> None:
    body = b'{"ok":true}'
    mw = ZstdMiddleware(_make_app([(body, False)]), minimum_size=_MIN_SIZE)
    sent = await _drive(mw, accept_encoding="zstd")
    assert b"content-encoding" not in _headers_of(sent)
    assert _body_of(sent) == body


async def test_middleware_passes_through_without_accept_encoding() -> None:
    body = b'{"items":["' + b"x" * (_MIN_SIZE * 2) + b'"]}'
    mw = ZstdMiddleware(_make_app([(body, False)]), minimum_size=_MIN_SIZE)
    sent = await _drive(mw, accept_encoding=None)
    assert b"content-encoding" not in _headers_of(sent)
    assert _body_of(sent) == body


async def test_middleware_does_not_recompress_encoded_body() -> None:
    body = b"x" * (_MIN_SIZE * 2)
    mw = ZstdMiddleware(_make_app([(body, False)], content_encoding=b"br"), minimum_size=_MIN_SIZE)
    sent = await _drive(mw, accept_encoding="zstd")
    assert _headers_of(sent)[b"content-encoding"] == b"br"
    assert _body_of(sent) == body


async def test_middleware_streams_through_uncompressed() -> None:
    # A multi-chunk (more_body=True) response must not be buffered or compressed.
    first = b"a" * (_MIN_SIZE * 2)
    second = b"b" * (_MIN_SIZE * 2)
    mw = ZstdMiddleware(_make_app([(first, True), (second, False)]), minimum_size=_MIN_SIZE)
    sent = await _drive(mw, accept_encoding="zstd")
    assert b"content-encoding" not in _headers_of(sent)
    assert _body_of(sent) == first + second


# --- Wired into the real app -------------------------------------------------


async def test_list_response_is_zstd_compressed_end_to_end(client: AsyncClient, create_task: CreateTask) -> None:
    for i in range(12):
        await create_task(f"compression probe task {i}")
    resp = await client.get("/v1/tasks", headers={"Accept-Encoding": "zstd"})
    assert resp.status_code == 200
    assert resp.headers["content-encoding"] == "zstd"
    assert "accept-encoding" in resp.headers["vary"].lower()
    # httpx ships no zstd decoder here, so .content is the raw compressed payload.
    payload = zstd.decompress(resp.content)
    assert b"compression probe task" in payload


async def test_list_response_plain_without_accept_encoding(client: AsyncClient, create_task: CreateTask) -> None:
    for i in range(12):
        await create_task(f"plain probe task {i}")
    resp = await client.get("/v1/tasks")
    assert resp.status_code == 200
    assert "content-encoding" not in resp.headers
    assert len(resp.json()["items"]) == 12


async def test_small_error_response_not_compressed(client: AsyncClient) -> None:
    resp = await client.get(
        "/v1/tasks/00000000-0000-0000-0000-000000000000",
        headers={"Accept-Encoding": "zstd"},
    )
    assert resp.status_code == 404
    assert "content-encoding" not in resp.headers
