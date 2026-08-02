#!/bin/sh
# Apply DB migrations, then serve. Alembic upgrade is idempotent (no-op at head),
# so re-running on restart is safe. WEB_CONCURRENCY (default 1) sets uvicorn workers —
# multi-worker is safe now: Postgres + the advisory-lock guards replace the single-
# connection serialisation the in-memory SQLite build relied on.
set -e

alembic upgrade head

exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers "${WEB_CONCURRENCY:-1}"
