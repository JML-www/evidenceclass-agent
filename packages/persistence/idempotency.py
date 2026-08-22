"""Database-backed idempotency with request fingerprint conflict detection."""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Callable, Mapping
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from .models import IdempotencyRecord


class IdempotencyError(RuntimeError):
    error_code = "IDEMPOTENCY_ERROR"
    status_code = 500


class IdempotencyConflict(IdempotencyError):
    error_code = "IDEMPOTENCY_KEY_REUSED"
    status_code = 409


class IdempotencyTimeout(IdempotencyError):
    error_code = "IDEMPOTENCY_REQUEST_IN_PROGRESS"
    status_code = 409


class IdempotencyPreviousFailure(IdempotencyError):
    error_code = "IDEMPOTENCY_PREVIOUS_FAILURE"
    status_code = 409


def request_fingerprint(payload: Mapping[str, Any]) -> str:
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


Operation = Callable[[Session], dict[str, Any]]


class IdempotencyService:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        *,
        wait_timeout_seconds: float = 15.0,
        poll_seconds: float = 0.01,
    ) -> None:
        self._session_factory = session_factory
        self._wait_timeout_seconds = wait_timeout_seconds
        self._poll_seconds = poll_seconds

    def execute(
        self,
        *,
        workspace_id: UUID,
        endpoint: str,
        key: str,
        payload: Mapping[str, Any],
        operation: Operation,
        response_ref: Callable[[dict[str, Any]], str] | None = None,
    ) -> dict[str, Any]:
        if not key or len(key) > 255:
            raise ValueError("Idempotency-Key must contain 1..255 characters")
        fingerprint = request_fingerprint(payload)
        owner = self._reserve(workspace_id, endpoint, key, fingerprint)
        if not owner:
            return self._await_existing(workspace_id, endpoint, key, fingerprint)

        try:
            with self._session_factory() as session, session.begin():
                record = self._get(session, workspace_id, endpoint, key)
                response = operation(session)
                record.status = "SUCCEEDED"
                record.response_json = response
                if response_ref is not None:
                    record.response_ref = response_ref(response)
                return response
        except Exception as exc:
            with self._session_factory() as session, session.begin():
                record = self._get(session, workspace_id, endpoint, key)
                record.status = "FAILED"
                record.error_code = getattr(exc, "error_code", type(exc).__name__)
            raise

    def _reserve(self, workspace_id: UUID, endpoint: str, key: str, fingerprint: str) -> bool:
        try:
            with self._session_factory() as session, session.begin():
                session.add(
                    IdempotencyRecord(
                        workspace_id=workspace_id,
                        endpoint=endpoint,
                        idempotency_key=key,
                        request_hash=fingerprint,
                        status="PROCESSING",
                    )
                )
            return True
        except IntegrityError:
            return False

    def _await_existing(
        self, workspace_id: UUID, endpoint: str, key: str, fingerprint: str
    ) -> dict[str, Any]:
        deadline = time.monotonic() + self._wait_timeout_seconds
        while time.monotonic() < deadline:
            with self._session_factory() as session:
                record = self._get(session, workspace_id, endpoint, key)
                if record.request_hash != fingerprint:
                    raise IdempotencyConflict(
                        "the same Idempotency-Key was used with a different request"
                    )
                if record.status == "SUCCEEDED":
                    if record.response_json is None:
                        raise IdempotencyError("stored idempotent response is missing")
                    return dict(record.response_json)
                if record.status == "FAILED":
                    raise IdempotencyPreviousFailure(
                        f"the original request failed with {record.error_code or 'UNKNOWN'}"
                    )
            time.sleep(self._poll_seconds)
        raise IdempotencyTimeout("the original request is still processing")

    @staticmethod
    def _get(session: Session, workspace_id: UUID, endpoint: str, key: str) -> IdempotencyRecord:
        record = session.scalar(
            select(IdempotencyRecord).where(
                IdempotencyRecord.workspace_id == workspace_id,
                IdempotencyRecord.endpoint == endpoint,
                IdempotencyRecord.idempotency_key == key,
            )
        )
        if record is None:
            raise IdempotencyError("idempotency reservation disappeared")
        return record
