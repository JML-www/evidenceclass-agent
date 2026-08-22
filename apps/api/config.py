"""Small environment-backed settings object for the control-plane API."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AppSettings:
    database_url: str
    auth_secret: str
    worker_mode: str = "inline"
    create_schema: bool = True
    sse_max_seconds: int = 30
    object_store_backend: str = "memory"
    minio_endpoint: str = "127.0.0.1:9000"
    minio_access_key: str = "evidenceclass"
    minio_secret_key: str = "evidenceclass-secret"
    minio_bucket: str = "evidenceclass"
    minio_secure: bool = False

    @classmethod
    def from_env(cls) -> AppSettings:
        storage = Path(os.getenv("EVIDENCECLASS_STORAGE_DIR", "storage"))
        storage.mkdir(parents=True, exist_ok=True)
        return cls(
            database_url=os.getenv(
                "DATABASE_URL", f"sqlite:///{(storage / 'evidenceclass-api.db').as_posix()}"
            ),
            auth_secret=os.getenv("EVIDENCECLASS_AUTH_SECRET", "development-only-change-me"),
            worker_mode=os.getenv("EVIDENCECLASS_WORKER_MODE", "inline").lower(),
            create_schema=os.getenv("EVIDENCECLASS_CREATE_SCHEMA", "1") == "1",
            sse_max_seconds=max(1, int(os.getenv("EVIDENCECLASS_SSE_MAX_SECONDS", "30"))),
            object_store_backend=os.getenv("EVIDENCECLASS_OBJECT_STORE", "memory").lower(),
            minio_endpoint=os.getenv("MINIO_ENDPOINT", "127.0.0.1:9000"),
            minio_access_key=os.getenv("MINIO_ACCESS_KEY", "evidenceclass"),
            minio_secret_key=os.getenv("MINIO_SECRET_KEY", "evidenceclass-secret"),
            minio_bucket=os.getenv("MINIO_BUCKET", "evidenceclass"),
            minio_secure=os.getenv("MINIO_SECURE", "false").lower() == "true",
        )
