"""Run-scoped subprocess and temporary-file cleanup for cancellation/finalization."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from threading import RLock
from uuid import UUID


class RunResourceManager:
    def __init__(self, root: str | Path, run_id: UUID) -> None:
        self.root = Path(root).resolve()
        self.run_dir = (self.root / str(run_id)).resolve()
        if self.root not in self.run_dir.parents:
            raise ValueError("run directory escaped the configured temporary root")
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self._processes: list[subprocess.Popen] = []
        self._lock = RLock()

    def register_process(self, process: subprocess.Popen) -> None:
        with self._lock:
            self._processes.append(process)

    def cancelled_cleanup(self) -> None:
        with self._lock:
            for process in self._processes:
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=5)
            self._processes.clear()
        if self.run_dir.exists():
            shutil.rmtree(self.run_dir)

    def normal_cleanup(self) -> None:
        self.cancelled_cleanup()
