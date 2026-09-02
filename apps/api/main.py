"""FastAPI control plane for jobs, uploads, worker control, and progress events."""

from __future__ import annotations

import json
import re
from collections.abc import Generator
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any
from uuid import UUID, uuid4

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from apps.api.auth import TokenService, verify_password
from apps.api.config import AppSettings
from apps.api.schemas import (
    AnswerResponse,
    AssetResponse,
    BoundaryResponse,
    ConversationRequest,
    ConversationResponse,
    ConversationSummaryResponse,
    CreateJobRequest,
    FeedbackRequest,
    JobResponse,
    KnowledgeDocumentRequest,
    LoginRequest,
    LoginResponse,
    MessageRequest,
    MessageResponse,
    ReviewDecisionRequest,
    ReviewItemResponse,
    ReviewStatsResponse,
    StartResponse,
    UploadCompleteRequest,
    UploadInitRequest,
    UploadInitResponse,
)
from apps.worker.queue import CeleryTaskQueue, InProcessTaskQueue
from apps.worker.runtime import RuntimeWorker
from packages.agent_runtime.review import ReviewError
from packages.object_storage.service import (
    ObjectStorageService,
    StorageValidationError,
    UploadTicket,
)
from packages.object_storage.store import InMemoryObjectStore, MinioObjectStore, ObjectStore
from packages.persistence import (
    Base,
    JobEventService,
    OutboxPublisher,
    create_db_engine,
    make_session_factory,
)
from packages.persistence.jobs import JobLifecycleService, ResourceNotFound
from packages.persistence.models import (
    AgentRun,
    AgentStep,
    AnalysisJob,
    Conversation,
    EvidenceItem,
    KnowledgeChunk,
    KnowledgeDocument,
    MediaAsset,
    Message,
    ReviewAudit,
    ReviewItem,
    UploadSession,
    User,
    Workspace,
    WorkspaceMember,
)


class APIError(RuntimeError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        status_code: int = 400,
        retryable: bool = False,
        details: Any = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.retryable = retryable
        self.details = details or {}


bearer = HTTPBearer(auto_error=False)


def _error_payload(request_id: str, error: APIError) -> dict[str, Any]:
    return {
        "code": error.code,
        "message": error.message,
        "retryable": error.retryable,
        "request_id": request_id,
        "details": error.details,
    }


def _job_response(job: AnalysisJob) -> JobResponse:
    return JobResponse(
        job_id=job.id,
        workspace_id=job.workspace_id,
        mode=job.mode,
        status=job.status,
        progress=job.progress,
        created_at=job.created_at,
        updated_at=job.updated_at,
        error_code=job.error_code,
        error_message=job.error_message,
    )


def _message_response(message: Message) -> MessageResponse:
    return MessageResponse(
        message_id=message.id,
        conversation_id=message.conversation_id,
        role=message.role,
        content=message.content,
        citations=list(message.citations or []),
        evidence_available=bool(message.evidence_available),
        source=message.source,
        limitations=list(message.limitations or []),
        boundary=dict(message.boundary_json or {}),
        created_at=message.created_at,
    )


def _review_response(item: ReviewItem) -> ReviewItemResponse:
    payload = dict(item.original_payload_json or {})
    revised = item.revised_payload_json
    evidence_ids = payload.get("evidence_ids", [])
    if not isinstance(evidence_ids, list):
        evidence_ids = []
    return ReviewItemResponse(
        review_id=item.id,
        job_id=item.job_id,
        status=item.status,
        decision=item.decision,
        reason=item.note or str(payload.get("reason", "")),
        reviewer_id=item.reviewer_id,
        revision=item.revision,
        original_observation=dict(payload.get("observation", payload)),
        revised_observation=dict(revised) if isinstance(revised, dict) else None,
        evidence_ids=[str(value) for value in evidence_ids],
        created_at=item.created_at,
        decided_at=item.decided_at,
    )


def _workspace_id(session: Session, user_id: UUID, requested: str | None = None) -> UUID:
    if requested:
        try:
            workspace_id = UUID(requested)
        except ValueError:
            raise APIError(
                "INVALID_WORKSPACE", "workspace_id is not a UUID", status_code=422
            ) from None
        allowed = session.scalar(
            select(WorkspaceMember.workspace_id).where(
                WorkspaceMember.workspace_id == workspace_id, WorkspaceMember.user_id == user_id
            )
        )
        if allowed is None:
            owner = session.scalar(
                select(Workspace.id).where(
                    Workspace.id == workspace_id, Workspace.owner_id == user_id
                )
            )
            if owner is None:
                raise APIError(
                    "FORBIDDEN", "user is not a member of this workspace", status_code=403
                )
        return workspace_id
    member = session.scalar(
        select(WorkspaceMember.workspace_id)
        .where(WorkspaceMember.user_id == user_id)
        .order_by(WorkspaceMember.created_at.asc())
    )
    if member is not None:
        return member
    owner = session.scalar(
        select(Workspace.id)
        .where(Workspace.owner_id == user_id)
        .order_by(Workspace.created_at.asc())
    )
    if owner is None:
        raise APIError("WORKSPACE_REQUIRED", "user has no workspace", status_code=403)
    return owner


def create_app(
    settings: AppSettings | None = None,
    *,
    session_factory: sessionmaker[Session] | None = None,
    object_store: ObjectStore | None = None,
    task_queue: InProcessTaskQueue | CeleryTaskQueue | None = None,
) -> FastAPI:
    settings = settings or AppSettings.from_env()
    engine = None
    if session_factory is None:
        engine = create_db_engine(settings.database_url)
        if settings.create_schema:
            Base.metadata.create_all(engine)
        session_factory = make_session_factory(engine)
    store = object_store
    if store is None:
        if settings.object_store_backend == "minio":
            store = MinioObjectStore(
                endpoint=settings.minio_endpoint,
                access_key=settings.minio_access_key,
                secret_key=settings.minio_secret_key,
                bucket=settings.minio_bucket,
                secure=settings.minio_secure,
            )
        else:
            store = InMemoryObjectStore()
    storage = ObjectStorageService(store, session_factory)
    lifecycle = JobLifecycleService(session_factory)
    events = JobEventService(session_factory)
    outbox = OutboxPublisher(session_factory)
    worker = RuntimeWorker(session_factory)
    if task_queue is not None:
        queue = task_queue
    elif settings.worker_mode == "celery":
        queue = CeleryTaskQueue()
    else:
        queue = InProcessTaskQueue(worker, auto_run=settings.worker_mode != "manual")
    tokens = TokenService(settings.auth_secret)
    app = FastAPI(title="EvidenceClass Agent API", version="0.2.0")
    app.state.settings = settings
    app.state.session_factory = session_factory
    app.state.lifecycle = lifecycle
    app.state.storage = storage
    app.state.events = events
    app.state.outbox = outbox
    app.state.queue = queue
    app.state.tokens = tokens

    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next):
        request.state.request_id = request.headers.get("X-Request-ID", str(uuid4()))
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        return response

    @app.exception_handler(APIError)
    async def api_error_handler(request: Request, exc: APIError):
        from fastapi.responses import JSONResponse

        return JSONResponse(
            status_code=exc.status_code, content=_error_payload(request.state.request_id, exc)
        )

    @app.exception_handler(HTTPException)
    async def http_error_handler(request: Request, exc: HTTPException):
        from fastapi.responses import JSONResponse

        error = APIError("HTTP_ERROR", str(exc.detail), status_code=exc.status_code)
        return JSONResponse(
            status_code=exc.status_code, content=_error_payload(request.state.request_id, error)
        )

    @app.exception_handler(ValidationError)
    async def validation_error_handler(request: Request, exc: ValidationError):
        from fastapi.responses import JSONResponse

        error = APIError(
            "INVALID_SCHEMA",
            "request schema validation failed",
            status_code=422,
            details=exc.errors(),
        )
        return JSONResponse(
            status_code=422, content=_error_payload(request.state.request_id, error)
        )

    @app.exception_handler(RequestValidationError)
    async def request_validation_error_handler(request: Request, exc: RequestValidationError):
        from fastapi.responses import JSONResponse

        error = APIError(
            "INVALID_SCHEMA",
            "request schema validation failed",
            status_code=422,
            details=exc.errors(),
        )
        return JSONResponse(
            status_code=422,
            content=_error_payload(request.state.request_id, error),
        )

    def current_user(
        credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    ) -> dict[str, Any]:
        if credentials is None or credentials.scheme.lower() != "bearer":
            raise APIError("UNAUTHENTICATED", "Bearer access token is required", status_code=401)
        try:
            return tokens.verify(credentials.credentials)
        except ValueError as exc:
            raise APIError("UNAUTHENTICATED", str(exc), status_code=401) from exc

    def scope(
        user: dict[str, Any] = Depends(current_user),
        x_workspace_id: str | None = Header(default=None, alias="X-Workspace-ID"),
    ) -> tuple[dict[str, Any], UUID]:
        with session_factory() as session:
            return user, _workspace_id(
                session, user["user_id"], x_workspace_id or user.get("workspace_id")
            )

    def get_job(session: Session, job_id: UUID, workspace_id: UUID) -> AnalysisJob:
        job = session.scalar(
            select(AnalysisJob).where(
                AnalysisJob.id == job_id,
                AnalysisJob.workspace_id == workspace_id,
                AnalysisJob.deleted_at.is_(None),
            )
        )
        if job is None:
            raise APIError("RESOURCE_NOT_FOUND", "job not found", status_code=404)
        return job

    def publish_outbox(target_run_id: UUID) -> str | None:
        task_ids: dict[UUID, str] = {}

        def send(topic: str, aggregate_id: UUID, _payload: dict[str, Any]) -> None:
            if topic != "agent.run.requested":
                raise ValueError(f"unsupported outbox topic: {topic}")
            task_id = queue.enqueue(aggregate_id)
            with session_factory() as session, session.begin():
                run = session.get(AgentRun, aggregate_id)
                if run is not None:
                    run.worker_task_id = task_id
            task_ids[aggregate_id] = task_id

        outbox.publish_pending(send)
        return task_ids.get(target_run_id)

    @app.get("/health/live")
    def health_live() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/health/ready")
    def health_ready() -> dict[str, str]:
        try:
            with session_factory() as session:
                session.execute(select(1))
        except Exception as exc:  # noqa: BLE001
            raise APIError(
                "NOT_READY",
                "database is not ready",
                status_code=503,
                retryable=True,
                details={"error": type(exc).__name__},
            ) from exc
        return {"status": "ready"}

    @app.post("/api/v1/auth/login", response_model=LoginResponse)
    def login(payload: LoginRequest) -> LoginResponse:
        with session_factory() as session:
            user = session.scalar(select(User).where(User.email == payload.email))
            if (
                user is None
                or user.status != "ACTIVE"
                or not verify_password(payload.password, user.password_hash)
            ):
                raise APIError(
                    "INVALID_CREDENTIALS", "email or password is incorrect", status_code=401
                )
            workspace = session.scalar(
                select(WorkspaceMember.workspace_id)
                .where(WorkspaceMember.user_id == user.id)
                .order_by(WorkspaceMember.created_at.asc())
            )
            workspace = workspace or session.scalar(
                select(Workspace.id)
                .where(Workspace.owner_id == user.id)
                .order_by(Workspace.created_at.asc())
            )
            token = tokens.issue(user_id=user.id, workspace_id=workspace)
            return LoginResponse(access_token=token, user_id=user.id, workspace_id=workspace)

    @app.post("/api/v1/jobs", response_model=JobResponse, status_code=201)
    def create_job(
        payload: CreateJobRequest,
        x_idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
        sc=Depends(scope),
    ):
        user, workspace_id = sc
        key = x_idempotency_key or str(uuid4())
        try:
            created = lifecycle.create_job(
                workspace_id=workspace_id,
                mode=payload.mode,
                idempotency_key=key,
                request=payload.model_dump(),
            )
        except Exception as exc:
            raise _map_domain_error(exc) from exc
        with session_factory() as session:
            return _job_response(get_job(session, UUID(created["job_id"]), workspace_id))

    @app.get("/api/v1/jobs", response_model=list[JobResponse])
    def list_jobs(sc=Depends(scope)):
        _user, workspace_id = sc
        with session_factory() as session:
            jobs = session.scalars(
                select(AnalysisJob)
                .where(AnalysisJob.workspace_id == workspace_id, AnalysisJob.deleted_at.is_(None))
                .order_by(AnalysisJob.created_at.desc())
            ).all()
            return [_job_response(job) for job in jobs]

    @app.get("/api/v1/jobs/{job_id}", response_model=JobResponse)
    def read_job(job_id: UUID, sc=Depends(scope)):
        _user, workspace_id = sc
        with session_factory() as session:
            return _job_response(get_job(session, job_id, workspace_id))

    @app.post("/api/v1/jobs/{job_id}/start", response_model=StartResponse)
    def start_job(
        job_id: UUID,
        x_idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
        sc=Depends(scope),
    ):
        _user, workspace_id = sc
        try:
            result = lifecycle.start_job(
                workspace_id=workspace_id,
                job_id=job_id,
                idempotency_key=x_idempotency_key or str(uuid4()),
            )
        except Exception as exc:
            raise _map_domain_error(exc) from exc
        task_id = publish_outbox(UUID(result["run_id"]))
        return StartResponse(**result, task_id=task_id)

    @app.post("/api/v1/jobs/{job_id}/cancel", response_model=JobResponse)
    def cancel_job(job_id: UUID, sc=Depends(scope)):
        _user, workspace_id = sc
        try:
            with session_factory() as session:
                run = session.scalar(
                    select(AgentRun)
                    .join(AnalysisJob, AgentRun.job_id == AnalysisJob.id)
                    .where(
                        AgentRun.job_id == job_id,
                        AgentRun.active_slot == "active",
                        AnalysisJob.workspace_id == workspace_id,
                    )
                )
                task_id = run.worker_task_id if run is not None else None
            lifecycle.cancel_job(workspace_id=workspace_id, job_id=job_id)
            if task_id:
                queue.cancel(task_id)
        except Exception as exc:
            raise _map_domain_error(exc) from exc
        with session_factory() as session:
            job = get_job(session, job_id, workspace_id)
            return _job_response(job)

    @app.post("/api/v1/jobs/{job_id}/retry", response_model=StartResponse)
    def retry_job(
        job_id: UUID,
        x_idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
        sc=Depends(scope),
    ):
        _user, workspace_id = sc
        try:
            result = lifecycle.retry_job(
                workspace_id=workspace_id,
                job_id=job_id,
                idempotency_key=x_idempotency_key or str(uuid4()),
            )
        except Exception as exc:
            raise _map_domain_error(exc) from exc
        return StartResponse(**result, task_id=publish_outbox(UUID(result["run_id"])))

    @app.post("/api/v1/jobs/{job_id}/rerun", response_model=StartResponse)
    def rerun_job(
        job_id: UUID,
        x_idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
        sc=Depends(scope),
    ):
        _user, workspace_id = sc
        try:
            result = lifecycle.rerun_job(
                workspace_id=workspace_id,
                job_id=job_id,
                idempotency_key=x_idempotency_key or str(uuid4()),
            )
        except Exception as exc:
            raise _map_domain_error(exc) from exc
        return StartResponse(**result, task_id=publish_outbox(UUID(result["run_id"])))

    @app.post(
        "/api/v1/jobs/{job_id}/assets/uploads", response_model=UploadInitResponse, status_code=201
    )
    def init_upload(job_id: UUID, payload: UploadInitRequest, sc=Depends(scope)):
        _user, workspace_id = sc
        try:
            ticket = storage.issue_upload(
                workspace_id=workspace_id,
                job_id=job_id,
                expected_mime=payload.expected_mime,
                max_size_bytes=payload.max_size_bytes,
            )
        except Exception as exc:
            raise _map_domain_error(exc) from exc
        upload_id = uuid4()
        with session_factory() as session, session.begin():
            session.add(
                UploadSession(
                    id=upload_id,
                    job_id=job_id,
                    object_key=ticket.object_key,
                    expected_mime=ticket.expected_mime,
                    max_size_bytes=ticket.max_size_bytes,
                    expires_at=ticket.expires_at,
                    role=payload.role,
                )
            )
        return UploadInitResponse(
            upload_id=upload_id,
            object_key=ticket.object_key,
            upload_url=ticket.upload_url,
            expected_mime=ticket.expected_mime,
            max_size_bytes=ticket.max_size_bytes,
            expires_at=ticket.expires_at,
        )

    @app.post(
        "/api/v1/jobs/{job_id}/assets/uploads/{upload_id}/complete", response_model=AssetResponse
    )
    def complete_upload(
        job_id: UUID, upload_id: UUID, payload: UploadCompleteRequest, sc=Depends(scope)
    ):
        _user, workspace_id = sc
        with session_factory() as session:
            job = get_job(session, job_id, workspace_id)
            upload = session.get(UploadSession, upload_id)
            if upload is None or upload.job_id != job.id or upload.status != "ISSUED":
                raise APIError("RESOURCE_NOT_FOUND", "upload session not found", status_code=404)
            ticket = UploadTicket(
                workspace_id=workspace_id,
                job_id=job.id,
                object_key=upload.object_key,
                upload_url="",
                expected_mime=upload.expected_mime,
                max_size_bytes=upload.max_size_bytes,
                expires_at=upload.expires_at,
            )
        try:
            asset = storage.complete_upload(
                ticket,
                expected_size_bytes=payload.expected_size_bytes,
                expected_sha256=payload.expected_sha256,
                role=upload.role,
            )
        except Exception as exc:
            raise _map_domain_error(exc) from exc
        with session_factory() as session, session.begin():
            row = session.get(UploadSession, upload_id)
            if row is not None:
                row.status = "COMPLETED"
        return AssetResponse(
            asset_id=asset.id,
            role=asset.role,
            mime=asset.mime,
            size_bytes=asset.size_bytes,
            sha256=asset.sha256,
        )

    @app.get("/api/v1/jobs/{job_id}/assets", response_model=list[AssetResponse])
    def list_assets(job_id: UUID, sc=Depends(scope)):
        _user, workspace_id = sc
        with session_factory() as session:
            get_job(session, job_id, workspace_id)
            assets = session.scalars(
                select(MediaAsset)
                .where(MediaAsset.job_id == job_id)
                .order_by(MediaAsset.created_at.asc())
            ).all()
        return [
            AssetResponse(
                asset_id=a.id, role=a.role, mime=a.mime, size_bytes=a.size_bytes, sha256=a.sha256
            )
            for a in assets
        ]

    @app.get("/api/v1/jobs/{job_id}/events")
    async def job_events(
        request: Request,
        job_id: UUID,
        last_event_id: int = Header(default=0, alias="Last-Event-ID"),
        sc=Depends(scope),
    ):
        _user, workspace_id = sc
        with session_factory() as session:
            get_job(session, job_id, workspace_id)
        rows = events.list_after(job_id=job_id, last_event_id=last_event_id)

        async def stream() -> Generator[str, None, None]:
            for row in rows:
                if await request.is_disconnected():
                    return
                data = json.dumps(row, ensure_ascii=False)
                yield f"id: {row['event_id']}\nevent: {row['type']}\ndata: {data}\n\n"
            yield ": heartbeat\n\n"

        return StreamingResponse(
            stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.get("/api/v1/jobs/{job_id}/agent-runs")
    def list_runs(job_id: UUID, sc=Depends(scope)):
        _user, workspace_id = sc
        with session_factory() as session:
            get_job(session, job_id, workspace_id)
            runs = session.scalars(
                select(AgentRun)
                .where(AgentRun.job_id == job_id)
                .order_by(AgentRun.created_at.asc())
            ).all()
            return [
                {
                    "run_id": str(r.id),
                    "status": r.status,
                    "graph_version": r.graph_version,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                }
                for r in runs
            ]

    @app.get("/api/v1/jobs/{job_id}/evidence")
    def list_evidence(job_id: UUID, sc=Depends(scope)):
        from packages.persistence.models import EvidenceItem

        _user, workspace_id = sc
        with session_factory() as session:
            get_job(session, job_id, workspace_id)
            items = session.scalars(
                select(EvidenceItem)
                .where(EvidenceItem.job_id == job_id)
                .order_by(EvidenceItem.created_at.asc())
            ).all()
            return [
                {
                    "evidence_id": item.evidence_id,
                    "source_ref": item.source_ref,
                    "fact": item.fact,
                    "limitations": item.limitations,
                }
                for item in items
            ]

    @app.get("/api/v1/jobs/{job_id}/artifacts")
    def list_artifacts(job_id: UUID, sc=Depends(scope)):
        from packages.persistence.models import Artifact

        _user, workspace_id = sc
        with session_factory() as session:
            get_job(session, job_id, workspace_id)
            items = session.scalars(
                select(Artifact)
                .where(Artifact.job_id == job_id)
                .order_by(Artifact.created_at.asc())
            ).all()
            return [
                {
                    "artifact_id": str(item.id),
                    "kind": item.kind,
                    "mime": item.mime,
                    "version": item.version,
                    "size_bytes": item.size_bytes,
                    "sha256": item.sha256,
                }
                for item in items
            ]

    @app.get("/api/v1/agent-runs/{run_id}/steps")
    def list_steps(run_id: UUID, sc=Depends(scope)):
        _user, workspace_id = sc
        with session_factory() as session:
            run = session.scalar(
                select(AgentRun)
                .join(AnalysisJob, AgentRun.job_id == AnalysisJob.id)
                .where(AgentRun.id == run_id, AnalysisJob.workspace_id == workspace_id)
            )
            if run is None:
                raise APIError("RESOURCE_NOT_FOUND", "Agent run not found", status_code=404)
            steps = session.scalars(
                select(AgentStep)
                .where(AgentStep.run_id == run_id)
                .order_by(AgentStep.created_at.asc())
            ).all()
            return [
                {
                    "step_id": str(s.id),
                    "node": s.node,
                    "status": s.status,
                    "input_hash": s.input_hash,
                    "output_hash": s.output_hash,
                    "created_at": s.created_at.isoformat() if s.created_at else None,
                }
                for s in steps
            ]

    @app.post("/api/v1/review-items/{review_id}/decision")
    def review_decision(review_id: UUID, payload: ReviewDecisionRequest, sc=Depends(scope)):
        user, workspace_id = sc
        with session_factory() as session:
            item = session.scalar(
                select(ReviewItem)
                .join(AnalysisJob, ReviewItem.job_id == AnalysisJob.id)
                .where(ReviewItem.id == review_id, AnalysisJob.workspace_id == workspace_id)
            )
            if item is None:
                raise APIError("RESOURCE_NOT_FOUND", "review item not found", status_code=404)
            if not payload.note.strip():
                raise APIError(
                    "REVIEW_REASON_REQUIRED",
                    "an audit reason is required for every review decision",
                    status_code=422,
                )
            original_payload = dict(item.original_payload_json or {})
            revision = int(item.revision or 0) + 1
            job_id_for_audit = item.job_id
            audit_evidence_ids = original_payload.get("evidence_ids", [])
            if not isinstance(audit_evidence_ids, list):
                audit_evidence_ids = []
        from packages.persistence.agent_runtime import SqlReviewService

        try:
            SqlReviewService(session_factory).decide(
                review_id,
                reviewer_id=str(user["user_id"]),
                role="reviewer",
                decision=payload.decision,
                note=payload.note,
                revised_observation=payload.revised_observation,
            )
        except Exception as exc:
            raise _map_domain_error(exc) from exc
        with session_factory() as session, session.begin():
            item = session.get(ReviewItem, review_id)
            if item is not None:
                session.add(
                    ReviewAudit(
                        id=uuid4(),
                        review_id=review_id,
                        job_id=job_id_for_audit,
                        reviewer_id=str(user["user_id"]),
                        decision=payload.decision,
                        reason=payload.note.strip(),
                        original_payload_json=original_payload,
                        revised_payload_json=(
                            dict(payload.revised_observation)
                            if payload.revised_observation is not None
                            else None
                        ),
                        evidence_ids=[str(value) for value in audit_evidence_ids],
                        revision=revision,
                    )
                )
        return {"review_id": str(review_id), "status": "DECIDED", "decision": payload.decision}

    @app.get("/api/v1/review-items", response_model=list[ReviewItemResponse])
    def list_review_items(
        job_id: UUID | None = None,
        decision: str | None = None,
        reviewer_id: str | None = None,
        from_time: datetime | None = None,
        to_time: datetime | None = None,
        sc=Depends(scope),
    ):
        _user, workspace_id = sc
        with session_factory() as session:
            statement = select(ReviewItem).join(AnalysisJob, ReviewItem.job_id == AnalysisJob.id)
            statement = statement.where(AnalysisJob.workspace_id == workspace_id)
            if job_id is not None:
                # Scope the filter to this workspace before returning any row.
                get_job(session, job_id, workspace_id)
                statement = statement.where(ReviewItem.job_id == job_id)
            if decision is not None:
                statement = statement.where(ReviewItem.decision == decision)
            if reviewer_id is not None:
                statement = statement.where(ReviewItem.reviewer_id == reviewer_id)
            if from_time is not None:
                statement = statement.where(ReviewItem.created_at >= from_time)
            if to_time is not None:
                statement = statement.where(ReviewItem.created_at <= to_time)
            rows = session.scalars(statement.order_by(ReviewItem.created_at.asc())).all()
            return [_review_response(row) for row in rows]

    @app.get("/api/v1/review-items/stats", response_model=ReviewStatsResponse)
    def review_stats(job_id: UUID | None = None, sc=Depends(scope)):
        _user, workspace_id = sc
        with session_factory() as session:
            statement = select(ReviewItem).join(AnalysisJob, ReviewItem.job_id == AnalysisJob.id)
            statement = statement.where(AnalysisJob.workspace_id == workspace_id)
            if job_id is not None:
                get_job(session, job_id, workspace_id)
                statement = statement.where(ReviewItem.job_id == job_id)
            rows = session.scalars(statement).all()
            by_decision: dict[str, int] = {}
            for row in rows:
                if row.decision:
                    by_decision[row.decision] = by_decision.get(row.decision, 0) + 1
            return ReviewStatsResponse(
                total=len(rows),
                pending=sum(row.status == "PENDING" for row in rows),
                decided=sum(row.status == "DECIDED" for row in rows),
                by_decision=by_decision,
            )

    @app.get("/api/v1/review-items/{review_id}/audit")
    def review_audit(review_id: UUID, sc=Depends(scope)):
        _user, workspace_id = sc
        with session_factory() as session:
            item = session.scalar(
                select(ReviewItem)
                .join(AnalysisJob, ReviewItem.job_id == AnalysisJob.id)
                .where(ReviewItem.id == review_id, AnalysisJob.workspace_id == workspace_id)
            )
            if item is None:
                raise APIError("RESOURCE_NOT_FOUND", "review item not found", status_code=404)
            audits = session.scalars(
                select(ReviewAudit)
                .where(ReviewAudit.review_id == review_id)
                .order_by(ReviewAudit.created_at.asc())
            ).all()
            return [
                {
                    "audit_id": str(audit.id),
                    "review_id": str(audit.review_id),
                    "job_id": str(audit.job_id),
                    "reviewer_id": audit.reviewer_id,
                    "decision": audit.decision,
                    "reason": audit.reason,
                    "original_observation": audit.original_payload_json,
                    "revised_observation": audit.revised_payload_json,
                    "evidence_ids": audit.evidence_ids,
                    "revision": audit.revision,
                    "created_at": audit.created_at.isoformat() if audit.created_at else None,
                }
                for audit in audits
            ]

    @app.post("/api/v1/jobs/{job_id}/feedback", response_model=ReviewItemResponse, status_code=201)
    def create_feedback(job_id: UUID, payload: FeedbackRequest, sc=Depends(scope)):
        user, workspace_id = sc
        if not payload.reason.strip():
            raise APIError("REVIEW_REASON_REQUIRED", "an audit reason is required", status_code=422)
        with session_factory() as session:
            job = get_job(session, job_id, workspace_id)
            evidence_ids = [str(value) for value in payload.evidence_ids]
            duplicate = session.scalar(
                select(ReviewAudit.id)
                .where(
                    ReviewAudit.job_id == job.id,
                    ReviewAudit.reviewer_id == str(user["user_id"]),
                    ReviewAudit.decision == payload.decision,
                    ReviewAudit.reason == payload.reason.strip(),
                )
                .order_by(ReviewAudit.created_at.desc())
            )
            if duplicate is not None:
                raise APIError(
                    "DUPLICATE_FEEDBACK",
                    "the same feedback decision has already been recorded",
                    status_code=409,
                )
            if evidence_ids:
                known = set(
                    session.scalars(
                        select(EvidenceItem.evidence_id).where(
                            EvidenceItem.job_id == job.id,
                            EvidenceItem.evidence_id.in_(evidence_ids),
                        )
                    ).all()
                )
                if known != set(evidence_ids):
                    raise APIError(
                        "CROSS_JOB_EVIDENCE",
                        "feedback evidence must belong to the selected job",
                        status_code=403,
                    )
        from packages.persistence.agent_runtime import SqlReviewService

        review_id = SqlReviewService(session_factory).create(
            job_id=job_id,
            reason=payload.reason.strip(),
            risk="MEDIUM",
            observation={
                "observation": dict(payload.original_observation),
                "evidence_ids": evidence_ids,
                "reason": payload.reason.strip(),
            },
        )
        # A feedback request is an explicit decision event, so persist the
        # structured audit while retaining ReviewItem's original payload.
        try:
            SqlReviewService(session_factory).decide(
                review_id,
                reviewer_id=str(user["user_id"]),
                role="reviewer",
                decision=payload.decision,
                note=payload.reason.strip(),
                revised_observation=payload.revised_observation,
            )
        except Exception as exc:
            raise _map_domain_error(exc) from exc
        with session_factory() as session, session.begin():
            item = session.get(ReviewItem, review_id)
            if item is None:
                raise APIError("RESOURCE_NOT_FOUND", "review item not found", status_code=404)
            session.add(
                ReviewAudit(
                    id=uuid4(),
                    review_id=review_id,
                    job_id=job_id,
                    reviewer_id=str(user["user_id"]),
                    decision=payload.decision,
                    reason=payload.reason.strip(),
                    original_payload_json=dict(item.original_payload_json or {}),
                    revised_payload_json=(
                        dict(payload.revised_observation)
                        if payload.revised_observation is not None
                        else None
                    ),
                    evidence_ids=evidence_ids,
                    revision=item.revision,
                )
            )
            session.flush()
            return _review_response(item)

    @app.post("/api/v1/knowledge/documents", status_code=201)
    def create_knowledge_document(payload: KnowledgeDocumentRequest, sc=Depends(scope)):
        _user, workspace_id = sc
        with session_factory() as session, session.begin():
            document = KnowledgeDocument(
                id=uuid4(), workspace_id=workspace_id, **payload.model_dump()
            )
            session.add(document)
            session.flush()
            return {"document_id": str(document.id), "status": document.status}

    @app.get("/api/v1/knowledge/documents")
    def list_knowledge_documents(sc=Depends(scope)):
        _user, workspace_id = sc
        with session_factory() as session:
            docs = session.scalars(
                select(KnowledgeDocument)
                .where(KnowledgeDocument.workspace_id == workspace_id)
                .order_by(KnowledgeDocument.created_at.desc())
            ).all()
            return [
                {
                    "document_id": str(doc.id),
                    "source_id": doc.source_id,
                    "title": doc.title,
                    "version": doc.version,
                    "status": doc.status,
                }
                for doc in docs
            ]

    def _conversation(session: Session, conversation_id: UUID, workspace_id: UUID) -> Conversation:
        conversation = session.scalar(
            select(Conversation).where(
                Conversation.id == conversation_id, Conversation.workspace_id == workspace_id
            )
        )
        if conversation is None:
            raise APIError("RESOURCE_NOT_FOUND", "conversation not found", status_code=404)
        return conversation

    def _conversation_boundary(conversation: Conversation, workspace_id: UUID) -> dict[str, Any]:
        return {
            "workspace_id": str(workspace_id),
            "job_id": str(conversation.job_id) if conversation.job_id else None,
            "conversation_id": str(conversation.id),
            "allowed_sources": ["evidence_items", "deterministic_results", "published_knowledge"],
            "limitations": [
                "仅基于当前工作区与当前任务可见证据回答",
                "证据不足时不会猜测或补齐结论",
                "不展示模型私有思维链",
            ],
        }

    def _refresh_summary(session: Session, conversation: Conversation) -> None:
        messages = session.scalars(
            select(Message)
            .where(Message.conversation_id == conversation.id)
            .order_by(Message.created_at.asc(), Message.id.asc())
        ).all()
        if not messages:
            return
        # Keep a bounded, deterministic summary.  The summary is metadata only;
        # it is never used to widen the workspace/job authorization boundary.
        window = messages[-12:]
        def safe_text(value: str) -> str:
            # Conversation summaries are metadata, not a media or identity
            # store.  Remove common file/data/contact references before they are
            # persisted while retaining enough text for context continuity.
            value = re.sub(r"data:[^\s]+", "[redacted-data-ref]", value)
            value = re.sub(r"(?:[A-Za-z]:\\|/)[^\s]+", "[redacted-media-ref]", value)
            value = re.sub(r"\b[\w.+-]+@[\w.-]+\.\w+\b", "[redacted-contact]", value)
            value = re.sub(r"(?<!\d)(?:1[3-9]\d{9})(?!\d)", "[redacted-contact]", value)
            return value[:500]

        lines = [f"{message.role}: {safe_text(message.content)}" for message in window]
        summary = "\n".join(lines)
        encoded = summary.encode("utf-8")
        citation_ids: list[str] = []
        for message in window:
            for citation in message.citations or []:
                if not isinstance(citation, dict):
                    continue
                citation_id = citation.get("evidence_id") or citation.get("citation_id")
                if citation_id is not None and str(citation_id) not in citation_ids:
                    citation_ids.append(str(citation_id))
        conversation.summary_version = int(conversation.summary_version or 0) + 1
        conversation.summary_hash = sha256(encoded).hexdigest()
        conversation.summary_json = {
            "text": summary,
            "message_count": len(messages),
            "citation_ids": citation_ids,
            "workspace_id": str(conversation.workspace_id),
            "job_id": str(conversation.job_id) if conversation.job_id else None,
            "source_message_start": str(window[0].id),
            "source_message_end": str(window[-1].id),
            "version": conversation.summary_version,
        }
        conversation.summary_source_start = window[0].id
        conversation.summary_source_end = window[-1].id
        conversation.summary_updated_at = datetime.now(timezone.utc)

    def _answer_for_question(
        session: Session, conversation: Conversation, question: str, workspace_id: UUID
    ) -> tuple[str, list[dict[str, Any]], bool, str, list[str]]:
        limitations = [
            "回答仅使用当前 conversation 绑定任务的 EvidenceItem、确定性结果和已发布知识来源",
            "回答不代表诊断或对个体学生的评价",
        ]
        referenced_jobs = {
            token.casefold()
            for token in re.findall(r"job[_-][A-Za-z0-9-]+", question)
        }
        current_job = str(conversation.job_id).casefold() if conversation.job_id else None
        if referenced_jobs and (current_job is None or current_job not in referenced_jobs):
            return (
                "请求超出当前会话边界，无法访问或比较其他任务。请在对应任务的会话中提问。",
                [],
                False,
                "unavailable_fallback",
                limitations + ["检测到跨任务请求"],
            )
        if re.search(r"诊断|处分|排名|绩效|预测个人", question):
            return (
                "该请求超出产品能力边界，系统只提供群体级、可观察且有证据支持的课堂事实。",
                [],
                False,
                "unavailable_fallback",
                limitations + ["不支持个体诊断、排名、处分或绩效推断"],
            )
        evidence = []
        if conversation.job_id is not None:
            evidence = session.scalars(
                select(EvidenceItem)
                .where(EvidenceItem.job_id == conversation.job_id)
                .order_by(EvidenceItem.created_at.asc())
            ).all()
        if evidence:
            citations = [
                {
                    "evidence_id": item.evidence_id,
                    "source_ref": item.source_ref,
                    "fact": item.fact,
                    "limitations": item.limitations or [],
                }
                for item in evidence[:5]
            ]
            # Deterministic/mock adapter: no external model is invoked and the
            # answer explicitly identifies that provenance for the caller.
            facts = "；".join(item.fact for item in evidence[:3])
            answer = (
                f"基于当前任务的可用证据，相关观察包括：{facts}。"
                "这些观察仅描述可见事实，不能据此推断未提供的结果。"
            )
            return answer, citations, True, "deterministic/mock", limitations

        # A conversation may also use workspace-scoped knowledge, but only
        # chunks from an explicitly authorized and published document qualify.
        knowledge_rows = session.execute(
            select(KnowledgeChunk, KnowledgeDocument)
            .join(KnowledgeDocument, KnowledgeChunk.document_id == KnowledgeDocument.id)
            .where(
                KnowledgeDocument.workspace_id == workspace_id,
                KnowledgeDocument.status == "PUBLISHED",
                KnowledgeDocument.authorization_status == "AUTHORIZED",
            )
            .order_by(KnowledgeChunk.created_at.asc())
        ).all()
        if knowledge_rows:
            citations = [
                {
                    "citation_id": chunk.chunk_id,
                    "source_ref": document.source,
                    "document_id": str(document.id),
                    "chunk_id": chunk.chunk_id,
                    "page": chunk.page,
                    "version": document.version,
                    "fact": chunk.content,
                    "limitations": ["知识来源仅用于补充背景，不替代当前任务证据"],
                }
                for chunk, document in knowledge_rows[:5]
            ]
            facts = "；".join(str(item[0].content) for item in knowledge_rows[:3])
            answer = (
                "当前任务没有 EvidenceItem；以下仅依据当前工作区已授权、已发布的知识来源："
                f"{facts}。该回答不能推断本任务未提供的观察。"
            )
            return (
                answer,
                citations,
                True,
                "deterministic/mock",
                limitations + ["回答使用授权知识来源"],
            )

        return (
            (
                "证据不足，无法判断。当前任务没有可用于回答该问题的 EvidenceItem，"
                "当前工作区也没有可用的已授权知识来源；请先完成分析或补充经过授权的材料。"
            ),
            [],
            False,
            "unavailable_fallback",
            limitations + ["当前任务和工作区没有可用证据或授权知识"],
        )

    @app.post("/api/v1/conversations", response_model=ConversationResponse, status_code=201)
    def create_conversation(payload: ConversationRequest, sc=Depends(scope)):
        _user, workspace_id = sc
        with session_factory() as session, session.begin():
            if payload.job_id is not None:
                get_job(session, payload.job_id, workspace_id)
            conversation = Conversation(
                id=uuid4(), workspace_id=workspace_id, title=payload.title, job_id=payload.job_id
            )
            session.add(conversation)
            session.flush()
            return ConversationResponse(
                conversation_id=conversation.id,
                workspace_id=conversation.workspace_id,
                job_id=conversation.job_id,
                title=conversation.title,
                summary_version=0,
                summary=None,
                created_at=conversation.created_at,
                updated_at=conversation.updated_at,
            )

    @app.get("/api/v1/conversations", response_model=list[ConversationResponse])
    def list_conversations(job_id: UUID | None = None, sc=Depends(scope)):
        _user, workspace_id = sc
        with session_factory() as session:
            statement = select(Conversation).where(Conversation.workspace_id == workspace_id)
            if job_id is not None:
                # Validate the job first so a caller cannot use a foreign job as
                # a filter oracle.
                get_job(session, job_id, workspace_id)
                statement = statement.where(Conversation.job_id == job_id)
            rows = session.scalars(statement.order_by(Conversation.updated_at.desc())).all()
            return [
                ConversationResponse(
                    conversation_id=row.id,
                    workspace_id=row.workspace_id,
                    job_id=row.job_id,
                    title=row.title,
                    summary_version=row.summary_version,
                    summary=row.summary_json,
                    created_at=row.created_at,
                    updated_at=row.updated_at,
                )
                for row in rows
            ]

    @app.get("/api/v1/conversations/{conversation_id}", response_model=ConversationResponse)
    def read_conversation(conversation_id: UUID, sc=Depends(scope)):
        _user, workspace_id = sc
        with session_factory() as session:
            row = _conversation(session, conversation_id, workspace_id)
            return ConversationResponse(
                conversation_id=row.id,
                workspace_id=row.workspace_id,
                job_id=row.job_id,
                title=row.title,
                summary_version=row.summary_version,
                summary=row.summary_json,
                created_at=row.created_at,
                updated_at=row.updated_at,
            )

    @app.get(
        "/api/v1/conversations/{conversation_id}/messages",
        response_model=list[MessageResponse],
    )
    def list_messages(conversation_id: UUID, sc=Depends(scope)):
        _user, workspace_id = sc
        with session_factory() as session:
            _conversation(session, conversation_id, workspace_id)
            messages = session.scalars(
                select(Message)
                .where(Message.conversation_id == conversation_id)
                .order_by(Message.created_at.asc(), Message.id.asc())
            ).all()
            return [_message_response(message) for message in messages]

    def _create_answer(
        conversation_id: UUID, payload: MessageRequest, workspace_id: UUID
    ) -> AnswerResponse:
        with session_factory() as session, session.begin():
            conversation = _conversation(session, conversation_id, workspace_id)
            boundary = _conversation_boundary(conversation, workspace_id)
            user_message = Message(
                id=uuid4(), conversation_id=conversation_id, role="user", content=payload.content,
                citations=[], evidence_available=False, source="user", limitations=[],
                boundary_json=boundary, created_at=datetime.now(timezone.utc),
            )
            session.add(user_message)
            session.flush()
            answer, citations, available, source, limitations = _answer_for_question(
                session, conversation, payload.content, workspace_id
            )
            assistant_message = Message(
                id=uuid4(), conversation_id=conversation_id, role="assistant", content=answer,
                citations=citations, evidence_available=available, source=source,
                limitations=limitations, boundary_json=boundary,
                created_at=datetime.now(timezone.utc),
            )
            session.add(assistant_message)
            session.flush()
            _refresh_summary(session, conversation)
            session.flush()
            return AnswerResponse(
                conversation_id=conversation.id,
                user_message=_message_response(user_message),
                assistant_message=_message_response(assistant_message),
                answer=answer,
                citations=citations,
                evidence_available=available,
                source=source,
                limitations=limitations,
                boundary=BoundaryResponse(**boundary),
                summary_version=conversation.summary_version,
            )

    @app.post("/api/v1/conversations/{conversation_id}/messages", response_model=AnswerResponse)
    def create_message(conversation_id: UUID, payload: MessageRequest, sc=Depends(scope)):
        _user, workspace_id = sc
        return _create_answer(conversation_id, payload, workspace_id)

    @app.post("/api/v1/conversations/{conversation_id}/ask", response_model=AnswerResponse)
    def ask_conversation(conversation_id: UUID, payload: MessageRequest, sc=Depends(scope)):
        _user, workspace_id = sc
        return _create_answer(conversation_id, payload, workspace_id)

    @app.get(
        "/api/v1/conversations/{conversation_id}/summary",
        response_model=ConversationSummaryResponse,
    )
    def read_summary(conversation_id: UUID, sc=Depends(scope)):
        _user, workspace_id = sc
        with session_factory() as session:
            conversation = _conversation(session, conversation_id, workspace_id)
            if not conversation.summary_json or conversation.summary_updated_at is None:
                _refresh_summary(session, conversation)
                session.commit()
                session.refresh(conversation)
            if not conversation.summary_json or conversation.summary_updated_at is None:
                summary = "暂无会话摘要。"
                updated = datetime.now(timezone.utc)
                digest = sha256(summary.encode("utf-8")).hexdigest()
                version = 0
                start = end = None
            else:
                summary = str(conversation.summary_json.get("text", ""))
                updated = conversation.summary_updated_at
                digest = conversation.summary_hash or sha256(summary.encode("utf-8")).hexdigest()
                version = conversation.summary_version
                start = conversation.summary_source_start
                end = conversation.summary_source_end
            return ConversationSummaryResponse(
                conversation_id=conversation.id,
                version=version,
                summary=summary,
                summary_hash=digest,
                updated_at=updated,
                source_message_start=start,
                source_message_end=end,
                boundary=BoundaryResponse(**_conversation_boundary(conversation, workspace_id)),
            )

    return app


def _map_domain_error(exc: Exception) -> APIError:
    code = getattr(exc, "error_code", None) or getattr(exc, "code", None)
    if isinstance(exc, ResourceNotFound) or getattr(exc, "status_code", None) == 404:
        return APIError(code or "RESOURCE_NOT_FOUND", str(exc), status_code=404)
    if isinstance(exc, ReviewError):
        if "already" in str(exc).casefold():
            return APIError(
                "REVIEW_ALREADY_DECIDED",
                "review item already has a decision",
                status_code=409,
            )
        return APIError(code or "REVIEW_ERROR", str(exc), status_code=422)
    if isinstance(exc, (StorageValidationError, ValidationError)):
        return APIError(code or "INVALID_REQUEST", str(exc), status_code=422)
    if isinstance(exc, IntegrityError):
        return APIError("CONFLICT", "resource conflicts with an existing record", status_code=409)
    if getattr(exc, "status_code", None) == 409:
        return APIError(code or "CONFLICT", str(exc), status_code=409)
    return APIError(code or "INVALID_REQUEST", str(exc), status_code=400)


app = create_app()
