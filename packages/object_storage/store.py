"""Minimal object-store port with MinIO and deterministic in-memory adapters."""

from __future__ import annotations

import io
from dataclasses import dataclass
from datetime import timedelta
from threading import RLock
from typing import Protocol

from minio import Minio
from minio.commonconfig import CopySource


@dataclass(frozen=True)
class StoredObject:
    key: str
    size: int
    content_type: str


class ObjectStore(Protocol):
    def ensure_bucket(self) -> None: ...

    def presign_put(self, key: str, *, expires: timedelta) -> str: ...

    def presign_get(self, key: str, *, expires: timedelta) -> str: ...

    def stat(self, key: str) -> StoredObject: ...

    def read(self, key: str) -> bytes: ...

    def put(self, key: str, data: bytes, content_type: str) -> None: ...

    def copy(self, source_key: str, destination_key: str) -> None: ...

    def remove(self, key: str) -> None: ...

    def list(self, prefix: str) -> list[str]: ...


class MinioObjectStore:
    def __init__(
        self,
        *,
        endpoint: str,
        access_key: str,
        secret_key: str,
        bucket: str,
        secure: bool = False,
    ) -> None:
        self._client = Minio(
            endpoint,
            access_key=access_key,
            secret_key=secret_key,
            secure=secure,
        )
        self._bucket = bucket

    def ensure_bucket(self) -> None:
        if not self._client.bucket_exists(self._bucket):
            self._client.make_bucket(self._bucket)

    def presign_put(self, key: str, *, expires: timedelta) -> str:
        return self._client.presigned_put_object(self._bucket, key, expires=expires)

    def presign_get(self, key: str, *, expires: timedelta) -> str:
        return self._client.presigned_get_object(self._bucket, key, expires=expires)

    def stat(self, key: str) -> StoredObject:
        item = self._client.stat_object(self._bucket, key)
        return StoredObject(
            key=key,
            size=item.size,
            content_type=item.content_type or "application/octet-stream",
        )

    def read(self, key: str) -> bytes:
        response = self._client.get_object(self._bucket, key)
        try:
            return response.read()
        finally:
            response.close()
            response.release_conn()

    def put(self, key: str, data: bytes, content_type: str) -> None:
        self._client.put_object(
            self._bucket,
            key,
            io.BytesIO(data),
            len(data),
            content_type=content_type,
        )

    def copy(self, source_key: str, destination_key: str) -> None:
        self._client.copy_object(
            self._bucket,
            destination_key,
            CopySource(self._bucket, source_key),
        )

    def remove(self, key: str) -> None:
        self._client.remove_object(self._bucket, key)

    def list(self, prefix: str) -> list[str]:
        return [
            item.object_name
            for item in self._client.list_objects(self._bucket, prefix=prefix, recursive=True)
            if item.object_name is not None
        ]


class InMemoryObjectStore:
    """A thread-safe fake that exercises storage policy without network access."""

    def __init__(self, bucket: str = "test") -> None:
        self.bucket = bucket
        self._objects: dict[str, tuple[bytes, str]] = {}
        self._lock = RLock()

    def ensure_bucket(self) -> None:
        return None

    def presign_put(self, key: str, *, expires: timedelta) -> str:
        return f"memory://{self.bucket}/{key}?operation=put&expires={int(expires.total_seconds())}"

    def presign_get(self, key: str, *, expires: timedelta) -> str:
        return f"memory://{self.bucket}/{key}?operation=get&expires={int(expires.total_seconds())}"

    def stat(self, key: str) -> StoredObject:
        with self._lock:
            data, content_type = self._objects[key]
            return StoredObject(key=key, size=len(data), content_type=content_type)

    def read(self, key: str) -> bytes:
        with self._lock:
            return self._objects[key][0]

    def put(self, key: str, data: bytes, content_type: str) -> None:
        with self._lock:
            self._objects[key] = (bytes(data), content_type)

    def copy(self, source_key: str, destination_key: str) -> None:
        with self._lock:
            self._objects[destination_key] = self._objects[source_key]

    def remove(self, key: str) -> None:
        with self._lock:
            self._objects.pop(key, None)

    def list(self, prefix: str) -> list[str]:
        with self._lock:
            return sorted(key for key in self._objects if key.startswith(prefix))
