"""Construct a worker in a standalone Celery process."""

from __future__ import annotations

from apps.api.config import AppSettings
from packages.persistence import create_db_engine, make_session_factory

from .runtime import RuntimeWorker


def build_worker() -> RuntimeWorker:
    settings = AppSettings.from_env()
    engine = create_db_engine(settings.database_url)
    return RuntimeWorker(make_session_factory(engine))
