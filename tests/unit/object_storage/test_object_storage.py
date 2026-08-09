import hashlib
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from packages.object_storage import (
    InMemoryObjectStore,
    ObjectStorageService,
    StorageValidationError,
)
from packages.object_storage.service import StorageResourceNotFound
from packages.persistence import Base, create_db_engine, make_session_factory
from packages.persistence.models import AnalysisJob, Artifact, MediaAsset, User, Workspace

PNG = b"\x89PNG\r\n\x1a\n" + b"synthetic-pixels"


def _setup(tmp_path):
    engine = create_db_engine(f"sqlite:///{(tmp_path / 'objects.db').as_posix()}")
    Base.metadata.create_all(engine)
    sessions = make_session_factory(engine)
    user_id = uuid4()
    workspace_a, workspace_b = uuid4(), uuid4()
    job_a, job_b = uuid4(), uuid4()
    with sessions() as session, session.begin():
        session.add(
            User(id=user_id, email="storage@example.test", password_hash="test-only")
        )
        session.flush()
        session.add_all(
            [
                Workspace(id=workspace_a, name="A", owner_id=user_id),
                Workspace(id=workspace_b, name="B", owner_id=user_id),
            ]
        )
        session.flush()
        session.add_all(
            [
                AnalysisJob(
                    id=job_a,
                    workspace_id=workspace_a,
                    mode="image",
                    status="CREATED",
                ),
                AnalysisJob(
                    id=job_b,
                    workspace_id=workspace_b,
                    mode="image",
                    status="CREATED",
                ),
            ]
        )
    store = InMemoryObjectStore()
    return (
        engine,
        sessions,
        store,
        ObjectStorageService(store, sessions),
        workspace_a,
        workspace_b,
        job_a,
    )


def _upload(service, store, workspace_id, job_id):
    ticket = service.issue_upload(
        workspace_id=workspace_id,
        job_id=job_id,
        expected_mime="image/png",
        max_size_bytes=1024,
    )
    store.put(ticket.object_key, PNG, "image/png")
    return service.complete_upload(
        ticket,
        expected_size_bytes=len(PNG),
        expected_sha256=hashlib.sha256(PNG).hexdigest(),
    )


def test_interrupted_or_invalid_upload_never_creates_formal_asset(tmp_path):
    engine, sessions, store, service, workspace_a, _workspace_b, job_a = _setup(tmp_path)
    ticket = service.issue_upload(
        workspace_id=workspace_a,
        job_id=job_a,
        expected_mime="image/png",
        max_size_bytes=1024,
    )
    store.put(ticket.object_key, b"not-a-png", "image/png")
    with pytest.raises(StorageValidationError, match="declared MIME"):
        service.complete_upload(
            ticket,
            expected_size_bytes=9,
            expected_sha256=hashlib.sha256(b"not-a-png").hexdigest(),
        )
    with sessions() as session:
        assert session.scalar(select(func.count()).select_from(MediaAsset)) == 0
    engine.dispose()


def test_workspace_cannot_download_another_workspace_asset_and_keys_hide_filename(tmp_path):
    engine, _sessions, store, service, workspace_a, workspace_b, job_a = _setup(tmp_path)
    asset = _upload(service, store, workspace_a, job_a)
    assert str(workspace_a) in asset.object_key
    assert "original" not in asset.object_key
    assert "memory://" in service.download_url(workspace_id=workspace_a, asset_id=asset.id)
    with pytest.raises(StorageResourceNotFound):
        service.download_url(workspace_id=workspace_b, asset_id=asset.id)
    engine.dispose()


def test_duplicate_hash_policy_explicitly_retains_separate_assets(tmp_path):
    engine, sessions, store, service, workspace_a, _workspace_b, job_a = _setup(tmp_path)
    first = _upload(service, store, workspace_a, job_a)
    second = _upload(service, store, workspace_a, job_a)
    assert first.sha256 == second.sha256
    assert first.id != second.id
    assert first.object_key != second.object_key
    with sessions() as session:
        assert session.scalar(select(func.count()).select_from(MediaAsset)) == 2
    engine.dispose()


def test_artifacts_publish_manifest_last_and_cleanup_by_retention(tmp_path):
    engine, sessions, store, service, workspace_a, _workspace_b, job_a = _setup(tmp_path)
    asset = _upload(service, store, workspace_a, job_a)
    manifest = service.publish_artifacts(
        workspace_id=workspace_a,
        job_id=job_a,
        version="v1",
        contents={
            "report": ("text/markdown", b"# synthetic report\n"),
            "analysis": ("application/json", b'{"synthetic":true}'),
        },
    )
    assert store.list(f"temporary/{workspace_a}/{job_a}/") == []
    assert store.read(manifest["manifest_key"]).startswith(b'{"artifacts"')
    with sessions() as session:
        assert session.scalar(select(func.count()).select_from(Artifact)) == 3

    now = datetime.now(timezone.utc)
    service.schedule_job_deletion(
        workspace_id=workspace_a,
        job_id=job_a,
        retention=timedelta(hours=1),
        now=now,
    )
    assert service.purge_due_jobs(now=now + timedelta(minutes=59)) == []
    assert store.stat(asset.object_key).size == len(PNG)
    assert service.purge_due_jobs(now=now + timedelta(hours=1)) == [job_a]
    assert store.list(f"workspaces/{workspace_a}/jobs/{job_a}/") == []
    with sessions() as session:
        assert session.scalar(select(func.count()).select_from(MediaAsset)) == 0
        assert session.scalar(select(func.count()).select_from(Artifact)) == 0
    engine.dispose()
