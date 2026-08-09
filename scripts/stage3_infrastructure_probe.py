"""Write and verify persistence sentinels across PostgreSQL, Redis, and MinIO."""

from __future__ import annotations

import argparse
import os

from redis import Redis
from sqlalchemy import create_engine, text

from packages.object_storage import MinioObjectStore


def _required(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"{name} is required")
    return value


def _store() -> MinioObjectStore:
    return MinioObjectStore(
        endpoint=_required("MINIO_ENDPOINT"),
        access_key=_required("MINIO_ACCESS_KEY"),
        secret_key=_required("MINIO_SECRET_KEY"),
        bucket=_required("MINIO_BUCKET"),
        secure=os.getenv("MINIO_SECURE", "false").lower() == "true",
    )


def write(token: str) -> None:
    engine = create_engine(_required("DATABASE_URL"))
    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE IF NOT EXISTS stage3_persistence_probe "
                "(token VARCHAR(128) PRIMARY KEY)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO stage3_persistence_probe(token) VALUES (:token) "
                "ON CONFLICT (token) DO NOTHING"
            ),
            {"token": token},
        )
    engine.dispose()

    redis = Redis.from_url(_required("REDIS_URL"), decode_responses=True)
    redis.set(f"stage3:persistence:{token}", token)

    store = _store()
    store.ensure_bucket()
    store.put(f"stage3-persistence/{token}", token.encode(), "text/plain")


def verify(token: str) -> None:
    engine = create_engine(_required("DATABASE_URL"))
    with engine.connect() as connection:
        value = connection.scalar(
            text("SELECT token FROM stage3_persistence_probe WHERE token = :token"),
            {"token": token},
        )
    engine.dispose()
    if value != token:
        raise RuntimeError("PostgreSQL persistence sentinel is missing")

    redis = Redis.from_url(_required("REDIS_URL"), decode_responses=True)
    if redis.get(f"stage3:persistence:{token}") != token:
        raise RuntimeError("Redis persistence sentinel is missing")

    store = _store()
    if store.read(f"stage3-persistence/{token}") != token.encode():
        raise RuntimeError("MinIO persistence sentinel is missing")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("operation", choices=("write", "verify"))
    parser.add_argument("token")
    args = parser.parse_args()
    if args.operation == "write":
        write(args.token)
    else:
        verify(args.token)
    print(f"stage3_infrastructure_{args.operation}=ok")


if __name__ == "__main__":
    main()
