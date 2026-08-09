import os
from pathlib import Path

import pytest

from evals.model_gateway.run_real_vision_eval import run

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_REAL_MODEL_TESTS") != "1",
    reason="requires an explicit paid-model opt-in",
)


def test_ten_self_created_images_return_structured_observations(tmp_path):
    model = os.environ.get("OPENAI_MODEL", "")
    assert model, "OPENAI_MODEL must be explicit"
    output = Path(os.environ.get("REAL_MODEL_EVAL_OUTPUT", str(tmp_path)))
    report = run(model=model, output_dir=output, count=10)
    assert report["total"] == 10
    assert report["successes"] == 10
    assert report["schema_first_pass_rate"] == 1.0
    assert report["failure_classification"] == {}
    assert report["accuracy_claimed"] is False
