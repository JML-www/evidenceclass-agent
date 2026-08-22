import subprocess
import sys
from uuid import uuid4

from apps.worker.resources import RunResourceManager


def test_cancel_terminates_child_and_cleans_only_run_directory(tmp_path):
    manager = RunResourceManager(tmp_path / "worker-tmp", uuid4())
    keep = manager.root / "keep.txt"
    keep.write_text("not part of run", encoding="utf-8")
    temporary = manager.run_dir / "partial.bin"
    temporary.write_bytes(b"partial")
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    manager.register_process(child)

    manager.cancelled_cleanup()

    assert child.poll() is not None
    assert not manager.run_dir.exists()
    assert keep.read_text(encoding="utf-8") == "not part of run"
