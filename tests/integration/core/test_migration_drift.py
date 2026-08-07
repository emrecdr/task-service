"""Alembic owns the production schema; the suite builds its own with ``create_all``. That split
leaves one gap no existing gate closes.

``alembic check`` compares the migration against the model's *metadata*, and a partial index's
``postgresql_where`` predicate is not part of that comparison — verified, not assumed: dropping the
dead-letter clause from ``_DELIVERABLE`` and re-running ``alembic check`` still reports "No new
upgrade operations detected". The tests miss it from the other side, because they build their schema
from the model and never run the migration at all. So a predicate edited in one place and not the
other passes every gate green, and surfaces only in production as the relay's poll quietly losing
its index and sequential-scanning ``outbox`` on every tick.

This gate builds both schemas on the session's Postgres and compares the DDL Postgres itself
reports, which normalises the two spellings — a SQLAlchemy expression on one side, the migration's
raw ``sa.text()`` on the other — to the same string before comparison.
"""

import os
import subprocess
import sys
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

_REPO_ROOT = Path(__file__).parents[3]
_SCRATCH_DB = "migration_drift_check"

# ``alembic_version`` is Alembic's own bookkeeping table — it exists only in the migrated schema and
# is not part of the model, so it is excluded rather than reported as a difference every run.
_INDEX_DDL = text(
    "SELECT indexname, indexdef FROM pg_indexes "
    "WHERE schemaname = 'public' AND tablename <> 'alembic_version' "
    "ORDER BY indexname"
)


async def _index_ddl(url: str) -> list[tuple[str, str]]:
    """Every index Postgres reports for the public schema, as (name, definition)."""
    engine = create_async_engine(url, poolclass=NullPool)
    try:
        async with engine.connect() as conn:
            return [(str(row.indexname), str(row.indexdef)) for row in (await conn.execute(_INDEX_DDL)).all()]
    finally:
        await engine.dispose()


def _format_disagreement(migrated: list[tuple[str, str]], modelled: list[tuple[str, str]]) -> str:
    """Name the indexes that differ and show both definitions — a bare list comparison would dump
    every index in the schema and bury the one that actually drifted."""
    migrated_by_name, modelled_by_name = dict(migrated), dict(modelled)
    lines: list[str] = []
    for name in sorted(migrated_by_name.keys() | modelled_by_name.keys()):
        from_migration = migrated_by_name.get(name)
        from_model = modelled_by_name.get(name)
        if from_migration != from_model:
            lines.append(f"  {name}:\n    migration: {from_migration}\n    model:     {from_model}")
    return "\n".join(lines)


async def test_migration_and_model_agree_on_index_ddl(postgres_url: str) -> None:
    """The migration and the model must produce the same indexes, predicates included."""
    scratch_url = make_url(postgres_url).set(database=_SCRATCH_DB).render_as_string(hide_password=False)

    # AUTOCOMMIT: Postgres refuses CREATE/DROP DATABASE inside a transaction block.
    admin = create_async_engine(postgres_url, isolation_level="AUTOCOMMIT", poolclass=NullPool)
    try:
        async with admin.begin() as conn:
            await conn.execute(text(f"DROP DATABASE IF EXISTS {_SCRATCH_DB} WITH (FORCE)"))
            await conn.execute(text(f"CREATE DATABASE {_SCRATCH_DB}"))

        # A subprocess, not Alembic's Python API: ``alembic/env.py`` reads ``settings.database_url``
        # and overwrites whatever the Config carries, so the URL can only be redirected through the
        # environment — and ``settings`` is already bound in this process. It also runs migrations
        # exactly the way the Docker entrypoint does.
        migrate = subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=_REPO_ROOT,
            env={**os.environ, "DATABASE_URL": scratch_url},
            capture_output=True,
            text=True,
            check=False,
        )
        assert migrate.returncode == 0, f"alembic upgrade head failed:\n{migrate.stderr}"

        migrated = await _index_ddl(scratch_url)
        modelled = await _index_ddl(postgres_url)  # built by ``create_all`` in the session fixture

        assert migrated == modelled, (
            "Migration and model disagree on index DDL. ``alembic check`` cannot catch this — it "
            "does not compare partial-index predicates — so the migration needs updating by hand:\n"
            f"{_format_disagreement(migrated, modelled)}"
        )
    finally:
        async with admin.begin() as conn:
            await conn.execute(text(f"DROP DATABASE IF EXISTS {_SCRATCH_DB} WITH (FORCE)"))
        await admin.dispose()
