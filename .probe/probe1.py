import json
import sys
import time
from pathlib import Path

sys.path.insert(0, ".")

from evals.model_gateway.run_real_vision_eval import _data_url
from packages.model_gateway.contracts import InvocationContext, VisionRequest
from packages.model_gateway.local_qwen import LocalQwen35Adapter
from packages.model_gateway.raw_responses import DirectoryRawResponseSink

out = Path("runs/probe-qwen")
adapter = LocalQwen35Adapter(
    model_path=Path(r"E:/PYPJ/models/Qwen3.5-0.8B"),
    raw_response_sink=DirectoryRawResponseSink(out / "raw"),
)
ctx = InvocationContext(
    prompt_version="real-vision-smoke.v0.1",
    config_version="probe.v0.1",
    timeout_seconds=60.0,
    max_output_tokens=700,
)
req = VisionRequest(
    image_refs=[_data_url(3)],
    instruction=(
        "This is a self-created synthetic classroom diagram, not a real person. "
        "Blue marks the teacher and dark or green squares mark student icons. "
        "Red strokes may represent raised-hand markers. Return conservative observable "
        "counts, evidence, limitations, and only the visible region estimates."
    ),
    context=ctx,
)
t0 = time.time()
res = adapter.observe(req)
print("latency_ms", res.metadata.latency_ms, "wall", round(time.time() - t0, 1))
print("provider", res.metadata.provider, "model", res.metadata.model)
print("revision", res.metadata.model_revision)
print("usage", res.metadata.usage.model_dump())
print("parsed", json.dumps(res.parsed.model_dump(), ensure_ascii=False)[:1500])
