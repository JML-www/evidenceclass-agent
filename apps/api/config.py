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
    sse_heartbeat_seconds: int = 15
    object_store_backend: str = "memory"
    minio_endpoint: str = "127.0.0.1:9000"
    minio_access_key: str = "evidenceclass"
    minio_secret_key: str = "evidenceclass-secret"
    minio_bucket: str = "evidenceclass"
    minio_secure: bool = False
    cors_origins: tuple[str, ...] = ("http://127.0.0.1:5173", "http://localhost:5173")
    log_level: str = "INFO"
    queue_max_queued_per_workspace: int = 8
    queue_max_total_weight: int = 240
    queue_max_task_seconds: int = 3_600
    metrics_enabled: bool = True

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
            sse_heartbeat_seconds=max(
                1, int(os.getenv("EVIDENCECLASS_SSE_HEARTBEAT_SECONDS", "15"))
            ),
            object_store_backend=os.getenv("EVIDENCECLASS_OBJECT_STORE", "memory").lower(),
            minio_endpoint=os.getenv("MINIO_ENDPOINT", "127.0.0.1:9000"),
            minio_access_key=os.getenv("MINIO_ACCESS_KEY", "evidenceclass"),
            minio_secret_key=os.getenv("MINIO_SECRET_KEY", "evidenceclass-secret"),
            minio_bucket=os.getenv("MINIO_BUCKET", "evidenceclass"),
            minio_secure=os.getenv("MINIO_SECURE", "false").lower() == "true",
            cors_origins=tuple(
                item.strip()
                for item in os.getenv(
                    "EVIDENCECLASS_CORS_ORIGINS",
                    "http://127.0.0.1:5173,http://localhost:5173",
                ).split(",")
                if item.strip()
            ),
            log_level=os.getenv("EVIDENCECLASS_LOG_LEVEL", "INFO").upper(),
            queue_max_queued_per_workspace=max(
                1, int(os.getenv("EVIDENCECLASS_QUEUE_MAX_QUEUED", "8"))
            ),
            queue_max_total_weight=max(1, int(os.getenv("EVIDENCECLASS_QUEUE_MAX_WEIGHT", "240"))),
            queue_max_task_seconds=max(
                1, int(os.getenv("EVIDENCECLASS_QUEUE_MAX_TASK_SECONDS", "3600"))
            ),
            metrics_enabled=os.getenv("EVIDENCECLASS_METRICS_ENABLED", "1") == "1",
        )
