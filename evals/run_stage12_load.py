"""Queue-protection load probe for stage 12.

Fires many concurrent start requests at the control-plane API and asserts the
predictable-degradation contract: the API stays available, admitted work never
exceeds the configured ceiling, and the excess is rejected with a retryable
``QUEUE_BACKPRESSURE`` rather than silently deepening the queue.

This is the offline, in-process equivalent of the Locust/k6 scenario in the
stage-12 plan; it needs no external load generator or network listener.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx

from apps.api.auth import hash_password
from apps.api.config import AppSettings
from apps.api.main import create_app
from apps.worker.queue import InProcessTaskQueue
from apps.worker.runtime import RuntimeWorker
from packages.object_storage.store import InMemoryObjectStore
from packages.persistence import Base, create_db_engine, make_session_factory
from packages.persistence.models import User, Workspace, WorkspaceMember

ROOT = Path(__file__).resolve().parents[1]

WORKSPACE_LIMIT = 4
CONCURRENT_REQUESTS = 24


def _build_client(database: Path) -> tuple[httpx.AsyncClient, Any, dict[str, str]]:
    # Each probe run starts from an empty database so repeated runs are stable.
    for suffix in ("", "-wal", "-shm"):
        stale = Path(f"{database}{suffix}")
        if stale.exists():
            stale.unlink()
    engine = create_db_engine(f"sqlite:///{database.as_posix()}")
    Base.metadata.create_all(engine)
    sessions = make_session_factory(engine)
    user_id, workspace_id = uuid4(), uuid4()
    with sessions() as session, session.begin():
        session.add(
            User(id=user_id, email="load@example.test", password_hash=hash_password("load pass"))
        )
        session.flush()
        session.add(Workspace(id=workspace_id, name="Load probe", owner_id=user_id))
        session.flush()
        session.add(WorkspaceMember(workspace_id=workspace_id, user_id=user_id, role="OWNER"))
    worker = RuntimeWorker(sessions)
    queue = InProcessTaskQueue(worker, auto_run=False)
    app = create_app(
        AppSettings(
            database_url=f"sqlite:///{database.as_posix()}",
            auth_secret="load-secret",
            worker_mode="manual",
            create_schema=False,
            queue_max_queued_per_workspace=WORKSPACE_LIMIT,
            queue_max_total_weight=10_000,
        ),
        session_factory=sessions,
        object_store=InMemoryObjectStore(),
        task_queue=queue,
    )
    client = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://load.test"
    )
    return client, engine, {"workspace_id": str(workspace_id)}


async def _token(client: httpx.AsyncClient) -> str:
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "load@example.test", "password": "load pass"},
    )
    response.raise_for_status()
    return response.json()["access_token"]


async def _probe(database: Path) -> dict[str, Any]:
    client, engine, scope = _build_client(database)
    try:
        token = await _token(client)
        headers = {"Authorization": f"Bearer {token}", "Idempotency-Key": str(uuid4())}
        job_ids: list[str] = []
        for _ in range(CONCURRENT_REQUESTS):
            created = await client.post(
                "/api/v1/jobs",
                headers={**headers, "Idempotency-Key": str(uuid4())},
                json={
                    "mode": "video",
                    "goal": "load probe",
                    "metadata": {"duration_seconds": 300, "asset_count": 1},
                },
            )
            created.raise_for_status()
            job_ids.append(created.json()["job_id"])

        async def start(job_id: str) -> int:
            response = await client.post(
                f"/api/v1/jobs/{job_id}/start",
                headers={**headers, "Idempotency-Key": str(uuid4())},
            )
            return response.status_code

        async def health() -> int:
            return (await client.get("/health/live")).status_code

        health_during = await asyncio.gather(*(health() for _ in range(8)))
        statuses = await asyncio.gather(*(start(job_id) for job_id in job_ids))
        health_after = await client.get("/health/live")
        queue_status = await client.get("/api/v1/queue/status", headers=headers)
        snapshot = queue_status.json()
        metrics = (await client.get("/metrics")).text
        return {
            "concurrent_requests": CONCURRENT_REQUESTS,
            "workspace_limit": WORKSPACE_LIMIT,
            "admitted": sum(1 for code in statuses if code == 200),
            "rejected_backpressure": sum(1 for code in statuses if code == 429),
            "other_statuses": sorted({code for code in statuses if code not in {200, 429}}),
            "health_statuses_during": sorted(set(health_during)),
            "health_after": health_after.status_code,
            "queue_in_flight": snapshot["in_flight"],
            "queue_limit": snapshot["limits"]["max_queued_per_workspace"],
            "metrics_expose_status": "evidenceclass_queue_rejections_total" in metrics,
            "workspace_id": scope["workspace_id"],
        }
    finally:
        await client.aclose()
        engine.dispose()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the stage-12 queue-protection probe.")
    parser.add_argument(
        "--output",
        default=str(ROOT / "runs" / "stage-12" / "queue-load.json"),
        help="Where to write the JSON result (gitignored runs/ by default)",
    )
    args = parser.parse_args(argv)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    result = asyncio.run(_probe(output.parent / "queue-load.db"))
    passed = (
        result["admitted"] <= WORKSPACE_LIMIT
        and result["rejected_backpressure"] == CONCURRENT_REQUESTS - result["admitted"]
        and result["health_statuses_during"] == [200]
        and result["health_after"] == 200
        and result["queue_in_flight"] <= WORKSPACE_LIMIT
        and not result["other_statuses"]
    )
    result["passed"] = passed
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
