"""Raw model responses are stored by reference and never emitted to application logs."""

from __future__ import annotations

import os
from pathlib import Path
from threading import RLock
from typing import Protocol
from uuid import uuid4

from packages.object_storage.store import ObjectStore


class RawResponseSink(Protocol):
    def put(self, payload: bytes) -> str: ...


class InMemoryRawResponseSink:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self._lock = RLock()

    def put(self, payload: bytes) -> str:
        reference = f"memory://model-responses/{uuid4()}"
        with self._lock:
            self.objects[reference] = bytes(payload)
        return reference


class DirectoryRawResponseSink:
    """Local evaluation sink; the runs directory is excluded from Git."""

    def __init__(self, directory: str | Path) -> None:
        self._directory = Path(directory)

    def put(self, payload: bytes) -> str:
        self._directory.mkdir(parents=True, exist_ok=True)
        destination = self._directory / f"{uuid4()}.json"
        temporary = destination.with_suffix(".tmp")
        try:
            temporary.write_bytes(payload)
            os.replace(temporary, destination)
        finally:
            if temporary.exists():
                temporary.unlink()
        return str(destination.resolve())


class ObjectStoreRawResponseSink:
    def __init__(self, store: ObjectStore, *, prefix: str) -> None:
        normalized = prefix.strip("/")
        if not normalized or ".." in normalized.split("/"):
            raise ValueError("raw-response prefix must be a safe relative object prefix")
        self._store = store
        self._prefix = normalized

    def put(self, payload: bytes) -> str:
        key = f"{self._prefix}/{uuid4()}.json"
        self._store.put(key, payload, "application/json")
        return f"object://{key}"
