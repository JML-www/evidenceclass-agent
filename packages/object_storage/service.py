"""Upload verification, tenant isolation, retention, and manifest-last publication."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from packages.persistence.models import AnalysisJob, Artifact, MediaAsset

from .store import ObjectStore

ALLOWED_MIME_TYPES = {
    "application/json",
    "audio/wav",
    "image/jpeg",
    "image/png",
    "text/csv",
    "text/html",
    "text/markdown",
    "text/plain",
    "video/mp4",
}


class StorageError(RuntimeError):
    error_code = "OBJECT_STORAGE_ERROR"


class StorageResourceNotFound(StorageError):
    error_code = "OBJECT_NOT_FOUND"
    status_code = 404


class StorageValidationError(StorageError):
    error_code = "UPLOAD_VALIDATION_FAILED"
    status_code = 422


@dataclass(frozen=True)
class UploadTicket:
    workspace_id: UUID
    job_id: UUID
    object_key: str
    upload_url: str
    expected_mime: str
    max_size_bytes: int
    expires_at: datetime


@dataclass(frozen=True)
class PublishedArtifact:
    artifact_id: UUID
    kind: str
    object_key: str
    sha256: str
    size_bytes: int
    mime: str
    version: str


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _looks_like(data: bytes, mime: str) -> bool:
    if mime == "image/png":
        return data.startswith(b"\x89PNG\r\n\x1a\n")
    if mime == "image/jpeg":
        return data.startswith(b"\xff\xd8\xff") and data.endswith(b"\xff\xd9")
    if mime == "video/mp4":
        return len(data) >= 12 and data[4:12].startswith(b"ftyp")
    if mime == "audio/wav":
        return len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WAVE"
    if mime == "application/json":
        try:
            json.loads(data.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return False
        return True
    if mime.startswith("text/"):
        try:
            data.decode("utf-8")
        except UnicodeDecodeError:
            return False
        return True
    return False


class ObjectStorageService:
    """Keep object bytes out of SQL while enforcing SQL-owned authorization."""

    def __init__(self, store: ObjectStore, session_factory: sessionmaker[Session]) -> None:
        self._store = store
        self._sessions = session_factory
        self._store.ensure_bucket()

    def issue_upload(
        self,
        *,
        workspace_id: UUID,
        job_id: UUID,
        expected_mime: str,
        max_size_bytes: int,
        expires: timedelta = timedelta(minutes=15),
    ) -> UploadTicket:
        if expected_mime not in ALLOWED_MIME_TYPES:
            raise StorageValidationError("MIME type is not allowed")
        if max_size_bytes <= 0:
            raise ValueError("max_size_bytes must be positive")
        self._require_job(workspace_id, job_id)
        key = f"temporary/{workspace_id}/{job_id}/uploads/{uuid4()}"
        return UploadTicket(
            workspace_id=workspace_id,
            job_id=job_id,
            object_key=key,
            upload_url=self._store.presign_put(key, expires=expires),
            expected_mime=expected_mime,
            max_size_bytes=max_size_bytes,
            expires_at=datetime.now(timezone.utc) + expires,
        )

    def complete_upload(
        self,
        ticket: UploadTicket,
        *,
        expected_size_bytes: int,
        expected_sha256: str,
        role: str = "source",
    ) -> MediaAsset:
        self._require_job(ticket.workspace_id, ticket.job_id)
        expires_at = ticket.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) > expires_at:
            raise StorageValidationError("upload ticket has expired")
        stat = self._store.stat(ticket.object_key)
        data = self._store.read(ticket.object_key)
        if stat.size != len(data) or stat.size != expected_size_bytes:
            raise StorageValidationError("uploaded size does not match the completion request")
        if stat.size > ticket.max_size_bytes:
            raise StorageValidationError("uploaded object exceeds the permitted size")
        normalized_mime = stat.content_type.split(";", 1)[0].strip().lower()
        if normalized_mime != ticket.expected_mime:
            raise StorageValidationError("uploaded MIME does not match the upload ticket")
        if not _looks_like(data, normalized_mime):
            raise StorageValidationError("uploaded bytes do not match the declared MIME")
        digest = _sha256(data)
        if digest != expected_sha256.lower():
            raise StorageValidationError("uploaded SHA-256 does not match")

        asset_id = uuid4()
        final_key = f"workspaces/{ticket.workspace_id}/jobs/{ticket.job_id}/media/{asset_id}"
        self._store.copy(ticket.object_key, final_key)
        try:
            with self._sessions() as session, session.begin():
                asset = MediaAsset(
                    id=asset_id,
                    job_id=ticket.job_id,
                    role=role,
                    object_key=final_key,
                    sha256=digest,
                    mime=normalized_mime,
                    size_bytes=len(data),
                )
                session.add(asset)
                session.flush()
            self._store.remove(ticket.object_key)
            return asset
        except Exception:
            self._store.remove(final_key)
            raise

    def download_url(
        self,
        *,
        workspace_id: UUID,
        asset_id: UUID,
        expires: timedelta = timedelta(minutes=10),
    ) -> str:
        with self._sessions() as session:
            asset = session.scalar(
                select(MediaAsset)
                .join(AnalysisJob, MediaAsset.job_id == AnalysisJob.id)
                .where(
                    MediaAsset.id == asset_id,
                    AnalysisJob.workspace_id == workspace_id,
                    AnalysisJob.deleted_at.is_(None),
                )
            )
            if asset is None:
                raise StorageResourceNotFound("asset not found")
            return self._store.presign_get(asset.object_key, expires=expires)

    def publish_artifacts(
        self,
        *,
        workspace_id: UUID,
        job_id: UUID,
        version: str,
        contents: dict[str, tuple[str, bytes]],
    ) -> dict[str, Any]:
        self._require_job(workspace_id, job_id)
        if not contents or "manifest" in contents:
            raise ValueError("contents must be nonempty and must not reserve the manifest kind")
        token = uuid4()
        temporary_keys: list[str] = []
        final_keys: list[str] = []
        published: list[PublishedArtifact] = []
        manifest_key = (
            f"workspaces/{workspace_id}/jobs/{job_id}/artifacts/{version}/{token}.manifest.json"
        )
        try:
            for kind, (mime, data) in sorted(contents.items()):
                if mime not in ALLOWED_MIME_TYPES or not _looks_like(data, mime):
                    raise StorageValidationError(f"artifact {kind} failed MIME validation")
                artifact_id = uuid4()
                temporary_key = f"temporary/{workspace_id}/{job_id}/artifacts/{token}/{artifact_id}"
                final_key = (
                    f"workspaces/{workspace_id}/jobs/{job_id}/artifacts/{version}/{artifact_id}"
                )
                self._store.put(temporary_key, data, mime)
                temporary_keys.append(temporary_key)
                self._store.copy(temporary_key, final_key)
                final_keys.append(final_key)
                published.append(
                    PublishedArtifact(
                        artifact_id=artifact_id,
                        kind=kind,
                        object_key=final_key,
                        sha256=_sha256(data),
                        size_bytes=len(data),
                        mime=mime,
                        version=version,
                    )
                )

            manifest = {
                "schema_version": "artifact-manifest.v0.1",
                "workspace_id": str(workspace_id),
                "job_id": str(job_id),
                "version": version,
                "artifacts": [
                    {**asdict(item), "artifact_id": str(item.artifact_id)} for item in published
                ],
            }
            manifest_bytes = json.dumps(
                manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            ).encode("utf-8")
            self._store.put(manifest_key, manifest_bytes, "application/json")
            final_keys.append(manifest_key)
            manifest_artifact = PublishedArtifact(
                artifact_id=uuid4(),
                kind="manifest",
                object_key=manifest_key,
                sha256=_sha256(manifest_bytes),
                size_bytes=len(manifest_bytes),
                mime="application/json",
                version=version,
            )
            with self._sessions() as session, session.begin():
                for item in [*published, manifest_artifact]:
                    session.add(
                        Artifact(
                            id=item.artifact_id,
                            job_id=job_id,
                            kind=item.kind,
                            object_key=item.object_key,
                            sha256=item.sha256,
                            version=item.version,
                            size_bytes=item.size_bytes,
                            mime=item.mime,
                        )
                    )
            for key in temporary_keys:
                self._store.remove(key)
            return {**manifest, "manifest_key": manifest_key}
        except Exception:
            for key in [*temporary_keys, *final_keys]:
                self._store.remove(key)
            raise

    def schedule_job_deletion(
        self,
        *,
        workspace_id: UUID,
        job_id: UUID,
        retention: timedelta,
        now: datetime | None = None,
    ) -> datetime:
        if retention.total_seconds() < 0:
            raise ValueError("retention cannot be negative")
        current_time = now or datetime.now(timezone.utc)
        with self._sessions() as session, session.begin():
            job = self._find_job(session, workspace_id, job_id)
            job.deleted_at = current_time
            job.purge_after = current_time + retention
            return job.purge_after

    def purge_due_jobs(self, *, now: datetime | None = None) -> list[UUID]:
        current_time = now or datetime.now(timezone.utc)
        with self._sessions() as session:
            due = list(
                session.scalars(
                    select(AnalysisJob).where(
                        AnalysisJob.purge_after.is_not(None),
                        AnalysisJob.purge_after <= current_time,
                        AnalysisJob.objects_purged_at.is_(None),
                    )
                )
            )
            targets = [(job.id, job.workspace_id) for job in due]

        purged: list[UUID] = []
        for job_id, workspace_id in targets:
            prefixes = (
                f"temporary/{workspace_id}/{job_id}/",
                f"workspaces/{workspace_id}/jobs/{job_id}/",
            )
            for prefix in prefixes:
                for key in self._store.list(prefix):
                    self._store.remove(key)
            with self._sessions() as session, session.begin():
                job = self._find_job(session, workspace_id, job_id)
                for asset in session.scalars(select(MediaAsset).where(MediaAsset.job_id == job_id)):
                    session.delete(asset)
                for artifact in session.scalars(select(Artifact).where(Artifact.job_id == job_id)):
                    session.delete(artifact)
                job.objects_purged_at = current_time
            purged.append(job_id)
        return purged

    def _require_job(self, workspace_id: UUID, job_id: UUID) -> None:
        with self._sessions() as session:
            self._find_job(session, workspace_id, job_id)

    @staticmethod
    def _find_job(session: Session, workspace_id: UUID, job_id: UUID) -> AnalysisJob:
        job = session.scalar(
            select(AnalysisJob).where(
                AnalysisJob.id == job_id,
                AnalysisJob.workspace_id == workspace_id,
            )
        )
        if job is None:
            raise StorageResourceNotFound("job not found")
        return job
