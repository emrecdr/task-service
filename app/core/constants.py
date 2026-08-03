from enum import StrEnum
from typing import Final


class Environment(StrEnum):
    DEV = "dev"
    TEST = "test"
    QA = "qa"
    PROD = "prod"


class OrderDirection(StrEnum):
    ASC = "asc"
    DESC = "desc"


DEFAULT_LIST_LIMIT: Final[int] = 100
MAX_LIST_LIMIT: Final[int] = 500

# Signed int64 upper bound — the list ``offset`` cannot exceed what the driver binds.
INT64_MAX: Final[int] = 2**63 - 1

# Request-hardening defaults (operator-overridable via env — see app.core.config).
DEFAULT_MAX_REQUEST_BODY_BYTES: Final[int] = 1 * 1024 * 1024  # 1 MiB
DEFAULT_REQUEST_TIMEOUT_SECONDS: Final[float] = 30.0

# Responses at least this large are worth zstd-compressing; below it the framing
# overhead outweighs the savings (mirrors Starlette's gzip default).
ZSTD_MINIMUM_SIZE_BYTES: Final[int] = 500

# Async connection-pool sizing (per worker; env-overridable). Defaults mirror SQLAlchemy's
# QueuePool defaults so the knobs are additive. ``-1`` recycle = disabled (``pool_pre_ping``
# already evicts dead connections on checkout).
DEFAULT_DB_POOL_SIZE: Final[int] = 5
DEFAULT_DB_MAX_OVERFLOW: Final[int] = 10
DEFAULT_DB_POOL_RECYCLE_SECONDS: Final[int] = -1

# Server-enforced DB timeouts (ms) + pool-checkout timeout (s), kept below the request
# budget so a slow query, lock wait, or pool saturation fails fast (→ 503) and frees the
# connection instead of pinning a worker for the whole request. ``0`` disables the GUC.
DEFAULT_DB_STATEMENT_TIMEOUT_MS: Final[int] = 10_000
DEFAULT_DB_LOCK_TIMEOUT_MS: Final[int] = 5_000
DEFAULT_DB_POOL_TIMEOUT_SECONDS: Final[float] = 5.0
