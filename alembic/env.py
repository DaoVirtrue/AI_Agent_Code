# ─── Alembic Environment Configuration ────────────────────────
# Configured for async PostgreSQL with SQLAlchemy 2.0.
# Run with: alembic upgrade head / alembic downgrade -1
import asyncio
import os
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

# Add the project root to sys.path so we can import from src
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Alembic Config object, which provides access to ini values
config = context.config

# Set up Python logging from alembic.ini
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Import all models so Alembic can detect them for autogenerate
from src.core.database import BaseModel  # noqa: E402, F401
from src.models import *  # noqa: E402, F403

# Metadata from all registered models
target_metadata = BaseModel.metadata

# ─── Helper: replace async URL with sync URL for Alembic ──────


def get_sync_url() -> str:
    """
    Resolve the synchronous database URL.
    Checks environment variables first, then falls back to alembic.ini.
    Converts asyncpg URLs to psycopg2/sync format if needed.
    """
    env_url = os.environ.get("DATABASE_URL_SYNC") or os.environ.get("DATABASE_URL")

    if env_url:
        # Convert asyncpg to sync psycopg2 URL if needed
        url = env_url.replace("+asyncpg", "")
        url = url.replace("postgresql+psycopg2://", "postgresql://")
        return url

    # Fall back to alembic.ini value
    ini_url = config.get_main_option("sqlalchemy.url")
    if ini_url:
        return ini_url

    raise ValueError(
        "No database URL configured. Set DATABASE_URL_SYNC or "
        "sqlalchemy.url in alembic.ini"
    )


def run_migrations_offline() -> None:
    """
    Run migrations in 'offline' mode.

    Configures the context with just a URL, not an Engine.
    Calls to context.execute() emit the given SQL string to the
    script output. Useful for generating SQL scripts without
    connecting to the database.
    """
    url = get_sync_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """
    Run migrations in a synchronous context.
    This is called from within the async engine's run_sync() context.
    """
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
        transaction_per_migration=True,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """
    Create an async engine and run migrations synchronously inside it.
    This is the recommended pattern for async SQLAlchemy 2.0 migrations.
    """
    url = get_sync_url()
    # Convert the sync URL back to async for the async engine
    async_url = url.replace("postgresql://", "postgresql+asyncpg://")

    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = async_url

    connectable = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        echo=False,
        future=True,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """
    Run migrations in 'online' mode.

    In this scenario we need to create an Engine and associate a
    connection with the context. We use an async engine and call
    run_sync() on the connection to run migrations synchronously.
    """
    asyncio.run(run_async_migrations())


# ─── Entry Point ──────────────────────────────────────────────

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
