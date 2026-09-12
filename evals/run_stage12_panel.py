"""Headless operations-panel probe for stage 12.

Executes one short job end to end through the control-plane API, then reads the
Prometheus exposition to prove the panel shows the full per-stage timing of that
run — the acceptance criterion for step 12.3 without needing a Grafana instance.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from apps.api.auth import hash_password
from apps.api.config import AppSettings
from apps.api.main import create_app
from apps.worker.queue import InProcessTaskQueue
from apps.worker.runtime import RuntimeWorker
from packages.object_storage.store import InMemoryObjectStore
from packages.persistence import Base, create_db_engine, make_session_factory
from packages.persistence.models import User, Workspace, WorkspaceMember

ROOT = Path(__file__).resolve().parents[1]

REQUIRED_SERIES: tuple[str, ...] = (
    "evidenceclass_http_requests_total",
    "evidenceclass_agent_runs_total",
    "evidenceclass_queue_in_flight",
    "evidenceclass_stage_agent_overhead_milliseconds",
    "evidenceclass_stage_end_to_end_milliseconds",
)


def _client(database: Path) -> tuple[TestClient, Any, dict[str, str], Any]:
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
            User(id=user_id, email="panel@example.test", password_hash=hash_password("panel pass"))
        )
        session.flush()
        session.add(Workspace(id=workspace_id, name="Panel probe", owner_id=user_id))
        session.flush()
        session.add(WorkspaceMember(workspace_id=workspace_id, user_id=user_id, role="OWNER"))
    worker = RuntimeWorker(sessions)
    queue = InProcessTaskQueue(worker, auto_run=False)
    app = create_app(
        AppSettings(
            database_url=f"sqlite:///{database.as_posix()}",
            auth_secret="panel-secret",
            worker_mode="manual",
            create_schema=False,
        ),
        session_factory=sessions,
        object_store=InMemoryObjectStore(),
        task_queue=queue,
    )
    client = TestClient(app)
    token = client.post(
        "/api/v1/auth/login",
        json={"email": "panel@example.test", "password": "panel pass"},
    ).json()["access_token"]
    return client, app, {"Authorization": f"Bearer {token}"}, engine


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Probe the stage-12 metrics panel.")
    parser.add_argument(
        "--output",
        default=str(ROOT / "runs" / "stage-12" / "panel.json"),
        help="Where to write the JSON panel snapshot (gitignored runs/ by default)",
    )
    args = parser.parse_args(argv)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)

    client, app, headers, engine = _client(output.parent / "panel.db")
    try:
        created = client.post(
            "/api/v1/jobs",
            headers={**headers, "Idempotency-Key": "panel-create"},
            json={"mode": "image", "goal": "panel probe run"},
        )
        created.raise_for_status()
        job_id = created.json()["job_id"]
        started = client.post(
            f"/api/v1/jobs/{job_id}/start", headers={**headers, "Idempotency-Key": "panel-start"}
        )
        started.raise_for_status()
        run_id = UUID(started.json()["run_id"])
        run_result = app.state.queue.run_now(run_id)

        from packages.observability import STAGE_NAMES
        from packages.observability import metrics as metrics_registry

        body = client.get("/metrics").text
        registry = metrics_registry()
        stage_series = {
            name: f"evidenceclass_stage_{name.removesuffix('_ms')}_milliseconds"
            for name in STAGE_NAMES
        }
        observed_stage_series = sorted(
            series for series in stage_series.values() if f"{series}_count" in body
        )
        snapshot: dict[str, Any] = {
            "run_status": run_result.get("status"),
            "job_status": run_result.get("job_status"),
            "required_series": list(REQUIRED_SERIES),
            "missing_series": [name for name in REQUIRED_SERIES if name not in body],
            "observed_stage_series": observed_stage_series,
            "stage_medians_ms": {
                series: registry.histogram_summary(series)["avg"]
                for series in observed_stage_series
            },
            "queue_in_flight": registry.gauge_value("evidenceclass_queue_in_flight"),
            "agent_runs_succeeded": registry.counter_value(
                "evidenceclass_agent_runs_total", labels={"outcome": "succeeded"}
            ),
        }
        snapshot["passed"] = (
            run_result.get("status") == "COMPLETED"
            and not snapshot["missing_series"]
            and len(observed_stage_series) >= 2
        )
        output.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(snapshot, ensure_ascii=False))
        return 0 if snapshot["passed"] else 1
    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
