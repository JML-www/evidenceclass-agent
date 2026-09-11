"""Construct a worker in a standalone Celery process."""

from __future__ import annotations

from apps.api.config import AppSettings
from packages.object_storage import InMemoryObjectStore, MinioObjectStore, ObjectStorageService
from packages.persistence import create_db_engine, make_session_factory

from .runtime import RuntimeWorker


def build_worker() -> RuntimeWorker:
    settings = AppSettings.from_env()
    engine = create_db_engine(settings.database_url)
    sessions = make_session_factory(engine)
    store = (
        MinioObjectStore(
            endpoint=settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            bucket=settings.minio_bucket,
            secure=settings.minio_secure,
        )
        if settings.object_store_backend == "minio"
        else InMemoryObjectStore()
    )
    return RuntimeWorker(sessions, ObjectStorageService(store, sessions))
