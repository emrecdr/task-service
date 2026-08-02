# syntax=docker/dockerfile:1.7
#
# Production image for the Internal Task Service.
#
# Multi-stage build:
#   * ``builder`` resolves and installs runtime dependencies via uv into
#     ``/app/.venv`` — no project source needed (``--no-install-project``).
#   * ``runtime`` starts from a clean ``python:3.14-slim`` and copies only
#     the venv + application source, dropping ``uv``, ``pip`` install
#     metadata, and any bootstrap layers from the final image.
#
# Runs as non-root (UID 1000) per TIS §12; TZ=UTC at the container boundary
# guarantees the FRD §2.4 timestamp invariant regardless of host clock.

# =============================================================
# Stage 1 — builder: resolve dependencies into a venv via uv
# =============================================================
# Base image pinned by digest for reproducible, supply-chain-safe builds;
# Dependabot (docker ecosystem) keeps the digest current. Tag is retained for
# human readability — the digest is what actually resolves.
FROM python:3.14-slim@sha256:cea0e6040540fb2b965b6e7fb5ffa00871e632eef63719f0ea54bca189ce14a6 AS builder

# uv from PyPI; pin the project's tooling requirements via pyproject if
# stricter reproducibility is wanted at CI time.
RUN pip install --no-cache-dir uv

WORKDIR /app

# ``--no-install-project`` keeps the project source out of the dep-resolve
# step so the dependency layer caches independently of code changes. The
# runtime version is read at import time from ``app/__init__.py::__version__``
# (see :mod:`app.main`), so the project itself does not need to be installed
# into the venv — only its dependencies.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project


# =============================================================
# Stage 2 — runtime: minimal image with only venv + source
# =============================================================
FROM python:3.14-slim@sha256:cea0e6040540fb2b965b6e7fb5ffa00871e632eef63719f0ea54bca189ce14a6 AS runtime

# OCI metadata — picked up by GHCR, Trivy, Renovate, and similar tooling.
# CI can override ``revision``/``version`` at build time via ``--label``.
LABEL org.opencontainers.image.title="Internal Task Service" \
    org.opencontainers.image.description="Internal CRUD service for tasks (Phase 1)." \
    org.opencontainers.image.licenses="Proprietary"

WORKDIR /app

# Heaviest, least-volatile layer first — venv changes only when uv.lock does.
COPY --from=builder /app/.venv /app/.venv
COPY app ./app
# Alembic runs at container start (entrypoint) — it owns the Postgres schema.
COPY alembic ./alembic
COPY alembic.ini ./alembic.ini
COPY docker/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

EXPOSE 8000

# UTC is FRD §2.4 — set at the container so any os.environ-time read sees it.
# ``PYTHONUNBUFFERED`` flushes stdout/stderr immediately so container log
# tools see the structured logs in real time.
# ``PATH`` puts the project venv first so ``uvicorn`` resolves without ``uv``.
ENV APP_ENV=prod
ENV TZ=UTC
ENV PYTHONUNBUFFERED=1
ENV PATH="/app/.venv/bin:$PATH"
# uvicorn worker count; multi-worker is safe on Postgres + the advisory-lock guards.
ENV WEB_CONCURRENCY=1

# Non-root runtime user. ``/app`` and ``/app/.venv`` are owned by root from
# the COPY above; the app persists to Postgres over the network and writes
# nothing to the container filesystem, so no chown is needed. The venv's binaries are
# world-executable by default, so UID 1000 can launch them.
USER 1000:1000

# Baked into the image so raw ``docker run`` (and orchestrators without their
# own probe wiring) get liveness for free. Compose overrides this with tighter
# timings for the E2E smoke tests.
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/healthz').status == 200 else 1)"]

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
