"""Local asynchronous queue used for deterministic development and acceptance."""

from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from uuid import UUID, uuid4

from .runtime import RuntimeWorker


class InProcessTaskQueue:
    def __init__(
        self, worker: RuntimeWorker, *, auto_run: bool = True, max_workers: int = 2
    ) -> None:
        self.worker = worker
        self.auto_run = auto_run
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers, thread_name_prefix="evidenceclass-worker"
        )
        self._futures: dict[str, Future] = {}

    def enqueue(self, run_id: UUID) -> str:
        task_id = str(uuid4())
        if self.auto_run:
            self._futures[task_id] = self._executor.submit(self.worker.run, run_id)
        return task_id

    def run_now(self, run_id: UUID) -> dict[str, object]:
        return self.worker.run(run_id)

    def cancel(self, task_id: str) -> bool:
        future = self._futures.get(task_id)
        return future.cancel() if future is not None else False

    def shutdown(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)


class CeleryTaskQueue:
    """Thin producer adapter; worker processes execute the named Celery task."""

    def enqueue(self, run_id: UUID) -> str:
        from .celery_app import run_agent

        return str(run_agent.delay(str(run_id)).id)

    def cancel(self, task_id: str) -> bool:
        from .celery_app import celery_app

        celery_app.control.revoke(task_id, terminate=True)
        return True
