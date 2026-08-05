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

# Transactional-outbox relay (in-process poller; env-overridable). Domain events are written
# to the ``outbox`` table inside each write's own transaction, then this relay delivers them
# to listeners exactly-once-per-success (at-least-once overall) and prunes delivered rows.
DEFAULT_OUTBOX_POLL_INTERVAL_SECONDS: Final[float] = 1.0
DEFAULT_OUTBOX_BATCH_SIZE: Final[int] = 100
# After this many failed deliveries a row is dead-lettered: stamped ``dead_lettered_at``, kept
# for triage, never polled again and never auto-pruned (only *delivered* rows age out). Crossing
# the ceiling emits the error-level ``outbox_dead_lettered`` log event: alert on that.
# Retries carry no backoff (a deliberate omission — see TIS §8.2), so this count times
# ``POLL_INTERVAL`` *is* the outage a delivery survives: 300 ≈ 5 minutes, wide enough to ride
# out a transient listener or DB failure instead of dead-lettering the event within seconds.
DEFAULT_OUTBOX_MAX_RETRIES: Final[int] = 300
# Delivered rows are pruned once they are this old; the poll query rides a partial index on
# the deliverable rows so table growth never slows delivery between prunes.
DEFAULT_OUTBOX_RETENTION_DAYS: Final[int] = 7
DEFAULT_OUTBOX_CLEANUP_INTERVAL_SECONDS: Final[float] = 3600.0  # hourly
# Rows deleted per prune statement. Bounding the batch keeps each DELETE short: one lock set,
# one WAL burst, and dead tuples autovacuum can keep pace with — an unbounded delete over a
# large retention window would instead run long enough to hit ``db_statement_timeout_ms``.
OUTBOX_PURGE_BATCH_SIZE: Final[int] = 1000
# Batches one prune pass may run. The prune shares the relay's task, so while it runs nothing
# is delivered; bounding the pass keeps that pause short even against a large backlog (one built
# up while the relay was stopped, or after the retention window was widened). Pruning is
# incremental, so whatever is left simply goes on the next pass.
OUTBOX_PURGE_MAX_BATCHES: Final[int] = 20
# Truncate a stored ``last_error`` so one pathological driver message can't bloat a row.
OUTBOX_LAST_ERROR_MAX_LENGTH: Final[int] = 1000
