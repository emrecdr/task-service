from compression import zstd

from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

_CONTENT_ENCODING = "zstd"


def _q_is_zero(value: str) -> bool:
    """``q=0`` (any spelling — ``0``, ``0.0``, ``0.000``…) is an explicit refusal, RFC 9110 §12.5.3."""
    try:
        return float(value) <= 0
    except ValueError:
        return False


def _client_accepts_zstd(accept_encoding: str) -> bool:
    """True when the ``Accept-Encoding`` header advertises zstd with a non-zero q-value.

    A bare ``zstd`` (or ``zstd;q=<n>`` with ``n > 0``) opts in; ``zstd;q=0`` is an
    explicit refusal. Matches the coding token exactly so a header like ``zstdx``
    never counts as zstd.
    """
    for token in accept_encoding.split(","):
        coding, _, params = token.strip().partition(";")
        if coding.strip().lower() != _CONTENT_ENCODING:
            continue
        for param in params.split(";"):
            key, _, value = param.strip().partition("=")
            if key.strip().lower() == "q" and _q_is_zero(value.strip()):
                return False
        return True
    return False


class ZstdMiddleware:
    """Negotiated zstd response compression using Python 3.14's ``compression.zstd`` (PEP 784).

    Pure-ASGI rather than ``BaseHTTPMiddleware`` because it must rewrite the raw
    response body messages. It compresses a complete buffered body once it clears
    ``minimum_size`` and the client sent ``Accept-Encoding: zstd``; streaming,
    already-encoded, and sub-threshold responses pass through untouched.

    Must be installed as the **innermost** middleware (added first) so it wraps the
    router directly: ``BaseHTTPMiddleware`` re-frames responses into ``more_body``
    chunks, which this middleware treats as streaming and would decline to compress.
    """

    def __init__(self, app: ASGIApp, *, minimum_size: int) -> None:
        self.app = app
        self.minimum_size = minimum_size

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not _client_accepts_zstd(Headers(scope=scope).get("accept-encoding", "")):
            await self.app(scope, receive, send)
            return

        start_message: Message | None = None
        handled = False

        async def send_with_zstd(message: Message) -> None:
            nonlocal start_message, handled
            if message["type"] == "http.response.start":
                start_message = message
                return
            if message["type"] != "http.response.body":
                await send(message)
                return
            assert start_message is not None  # ASGI guarantees start precedes body
            if handled:
                # Streaming continuation already committed to pass-through.
                await send(message)
                return
            handled = True
            body: bytes = message.get("body", b"")
            headers = MutableHeaders(raw=start_message["headers"])
            if message.get("more_body", False) or "content-encoding" in headers or len(body) < self.minimum_size:
                await send(start_message)
                await send(message)
                return
            compressed = zstd.compress(body)
            headers["Content-Encoding"] = _CONTENT_ENCODING
            headers["Content-Length"] = str(len(compressed))
            headers.add_vary_header("Accept-Encoding")
            await send(start_message)
            await send({"type": "http.response.body", "body": compressed, "more_body": False})

        await self.app(scope, receive, send_with_zstd)
