import os
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from redis import Redis
from sqlalchemy import create_engine, text

from packages.object_storage import MinioObjectStore

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_STAGE3_INFRA_TESTS") != "1",
    reason="requires PostgreSQL, Redis, and MinIO",
)


def test_postgres_migration_redis_and_minio_round_trip():
    database_url = os.environ["DATABASE_URL"]
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(config, "head")
    command.check(config)
    engine = create_engine(database_url)
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT 1")) == 1

    redis = Redis.from_url(os.environ["REDIS_URL"], decode_responses=True)
    token = str(uuid4())
    redis.set(f"stage3:{token}", token, ex=60)
    assert redis.get(f"stage3:{token}") == token

    store = MinioObjectStore(
        endpoint=os.environ["MINIO_ENDPOINT"],
        access_key=os.environ["MINIO_ACCESS_KEY"],
        secret_key=os.environ["MINIO_SECRET_KEY"],
        bucket=os.environ["MINIO_BUCKET"],
        secure=os.getenv("MINIO_SECURE", "false").lower() == "true",
    )
    store.ensure_bucket()
    key = f"integration/{token}"
    store.put(key, token.encode(), "text/plain")
    assert store.read(key) == token.encode()
    store.remove(key)

    command.downgrade(config, "base")
    command.upgrade(config, "head")
    engine.dispose()
