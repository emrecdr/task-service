import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config
from sqlmodel import SQLModel

from alembic import context
from app.core.config import settings

# Import the app itself, not a hand-listed set of model modules: autogenerate diffs against
# whatever has registered on ``SQLModel.metadata``, so a list is only as complete as the last
# person to remember it. A model the app loads but the list omits is invisible to *both*
# guards — ``alembic check`` sees no drift (neither side knows the table) and the tests still
# pass (their schema is built by ``create_all`` over the app's own metadata), so the migration
# ships without it. Importing the app makes the two sets equal by construction.
import app.main  # noqa: F401

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# The one source of truth for the schema; the app + tests use this same metadata.
target_metadata = SQLModel.metadata


def run_migrations_offline() -> None:
    """Emit SQL without a live DB (``alembic upgrade --sql``)."""
    context.configure(
        url=settings.database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = settings.database_url
    connectable = async_engine_from_config(configuration, prefix="sqlalchemy.", poolclass=pool.NullPool)
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
