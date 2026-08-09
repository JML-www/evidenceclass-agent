import os
from pathlib import Path

import pytest

from evals.model_gateway.run_real_vision_eval import run_local_qwen

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_LOCAL_QWEN_TESTS") != "1",
    reason="requires the optional local Qwen3.5 GPU runtime",
)


def test_temporary_local_qwen_runs_ten_original_images(tmp_path):
    model_path = Path(os.environ.get("LOCAL_QWEN_MODEL_PATH", ""))
    assert model_path.is_dir(), "LOCAL_QWEN_MODEL_PATH must be explicit"
    output = Path(os.environ.get("LOCAL_QWEN_EVAL_OUTPUT", str(tmp_path)))
    report = run_local_qwen(model_path=model_path, output_dir=output, count=10)
    assert report["total"] == 10
    assert report["successes"] == 10
    assert report["failure_classification"] == {}
    assert report["accuracy_claimed"] is False
    assert report["model"].startswith("temporary-local:")
