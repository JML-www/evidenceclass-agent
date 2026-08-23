"""Alembic environment using the application metadata and DATABASE_URL."""

from __future__ import annotations

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from packages.persistence.models import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata
POSTGRES_ONLY_INDEXES = {"ix_knowledge_chunks_embedding_hnsw"}
# The stage-3 acceptance probe creates this short-lived table outside the
# application schema so it can verify PostgreSQL volume persistence.  It is
# intentionally not part of ``Base.metadata`` and therefore must not be
# reported as schema drift by ``alembic check`` while the probe is present.
RUNTIME_PROBE_TABLES = {"stage3_persistence_probe"}


def database_url() -> str:
    return os.environ.get("DATABASE_URL") or config.get_main_option("sqlalchemy.url")


def include_object(_object, name, type_, reflected, compare_to) -> bool:
    """Exclude implementation-only objects from autogenerate drift checks."""

    if type_ == "index" and name in POSTGRES_ONLY_INDEXES:
        return context.get_context().dialect.name == "postgresql"
    if type_ == "table" and name in RUNTIME_PROBE_TABLES:
        return not (reflected and compare_to is None)
    return True


def run_migrations_offline() -> None:
    context.configure(
        url=database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        include_object=include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    section = config.get_section(config.config_ini_section, {})
    section["sqlalchemy.url"] = database_url()
    connectable = engine_from_config(
        section,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            include_object=include_object,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
