# Performance baseline — EvidenceClass Agent v0.12.0

Generated `2026-09-12T07:36:15.033497+00:00` by `evals/run_stage12_benchmark.py`.

## Environment

- Python: `3.10.11` on `Windows-10-10.0.22621-SP0`
- Machine: `` / `unknown` · CPU count: 32
- Models: deterministic offline adapters only (provider calls: 0)
- Repeats per scenario: 5

## Results (median / p95, milliseconds unless stated)

| Scenario | Stage | p50 | p95 | min | max |
|----------|-------|-----|-----|-----|-----|
| `image-1080p` | `upload_ms` | 0.012 ms | 0.021 ms | 0.009 | 0.021 |
| `image-1080p` | `agent_overhead_ms` | 3.874 ms | 4.582 ms | 3.515 | 4.582 |
| `image-1080p` | `artifact_ms` | 0.547 ms | 0.569 ms | 0.535 | 0.569 |
| `image-1080p` | `end_to_end_ms` | 4.626 ms | 5.309 ms | 4.192 | 5.309 |
| `image-1080p` | `probe_ms` | n/a | n/a | n/a | n/a |
| `image-1080p` | `frame_extract_ms` | n/a | n/a | n/a | n/a |
| `image-1080p` | `asr_ms` | n/a | n/a | n/a | n/a |
| `image-1080p` | `ocr_ms` | n/a | n/a | n/a | n/a |
| `image-1080p` | `vlm_ms` | n/a | n/a | n/a | n/a |
| `image-1080p` | `retrieval_ms` | n/a | n/a | n/a | n/a |
| `image-1080p` | `peak_memory_mb` | 0.221 MB | 0.236 MB | 0.2 | 0.236 |
| `image-1080p` | `upload_bytes` | 992.0 B | 992.0 B | 992.0 | 992.0 |
| `video-2min` | `upload_ms` | 0.009 ms | 0.013 ms | 0.008 | 0.013 |
| `video-2min` | `agent_overhead_ms` | 3.535 ms | 4.033 ms | 3.466 | 4.033 |
| `video-2min` | `artifact_ms` | 0.59 ms | 0.631 ms | 0.551 | 0.631 |
| `video-2min` | `end_to_end_ms` | 4.314 ms | 4.893 ms | 4.258 | 4.893 |
| `video-2min` | `probe_ms` | n/a | n/a | n/a | n/a |
| `video-2min` | `frame_extract_ms` | n/a | n/a | n/a | n/a |
| `video-2min` | `asr_ms` | n/a | n/a | n/a | n/a |
| `video-2min` | `ocr_ms` | n/a | n/a | n/a | n/a |
| `video-2min` | `vlm_ms` | n/a | n/a | n/a | n/a |
| `video-2min` | `retrieval_ms` | n/a | n/a | n/a | n/a |
| `video-2min` | `peak_memory_mb` | 0.26 MB | 0.267 MB | 0.245 | 0.267 |
| `video-2min` | `upload_bytes` | 1784.0 B | 1784.0 B | 1784.0 | 1784.0 |
| `video-10min` | `upload_ms` | 0.012 ms | 0.016 ms | 0.01 | 0.016 |
| `video-10min` | `agent_overhead_ms` | 4.477 ms | 5.132 ms | 4.346 | 5.132 |
| `video-10min` | `artifact_ms` | 1.275 ms | 1.752 ms | 1.164 | 1.752 |
| `video-10min` | `end_to_end_ms` | 6.145 ms | 6.951 ms | 5.921 | 6.951 |
| `video-10min` | `probe_ms` | n/a | n/a | n/a | n/a |
| `video-10min` | `frame_extract_ms` | n/a | n/a | n/a | n/a |
| `video-10min` | `asr_ms` | n/a | n/a | n/a | n/a |
| `video-10min` | `ocr_ms` | n/a | n/a | n/a | n/a |
| `video-10min` | `vlm_ms` | n/a | n/a | n/a | n/a |
| `video-10min` | `retrieval_ms` | n/a | n/a | n/a | n/a |
| `video-10min` | `peak_memory_mb` | 0.302 MB | 0.304 MB | 0.29 | 0.304 |
| `video-10min` | `upload_bytes` | 5421.0 B | 5421.0 B | 5421.0 | 5421.0 |
| `video-46min-dual` | `upload_ms` | 0.021 ms | 0.024 ms | 0.02 | 0.024 |
| `video-46min-dual` | `agent_overhead_ms` | 7.725 ms | 8.081 ms | 7.26 | 8.081 |
| `video-46min-dual` | `artifact_ms` | 3.56 ms | 3.832 ms | 3.375 | 3.832 |
| `video-46min-dual` | `end_to_end_ms` | 12.353 ms | 12.966 ms | 12.228 | 12.966 |
| `video-46min-dual` | `probe_ms` | n/a | n/a | n/a | n/a |
| `video-46min-dual` | `frame_extract_ms` | n/a | n/a | n/a | n/a |
| `video-46min-dual` | `asr_ms` | n/a | n/a | n/a | n/a |
| `video-46min-dual` | `ocr_ms` | n/a | n/a | n/a | n/a |
| `video-46min-dual` | `vlm_ms` | n/a | n/a | n/a | n/a |
| `video-46min-dual` | `retrieval_ms` | n/a | n/a | n/a | n/a |
| `video-46min-dual` | `peak_memory_mb` | 0.602 MB | 0.608 MB | 0.596 | 0.608 |
| `video-46min-dual` | `upload_bytes` | 21875.0 B | 21875.0 B | 21875.0 | 21875.0 |

## Skipped stages and why

- `probe_ms` — needs a real media/model provider; reported as unknown, not estimated.
- `frame_extract_ms` — needs a real media/model provider; reported as unknown, not estimated.
- `asr_ms` — needs a real media/model provider; reported as unknown, not estimated.
- `ocr_ms` — needs a real media/model provider; reported as unknown, not estimated.
- `vlm_ms` — needs a real media/model provider; reported as unknown, not estimated.
- `retrieval_ms` — needs a real media/model provider; reported as unknown, not estimated.

## Limitations

- Model-dependent stages are reported as null; never as measured accuracy or latency.
- Inputs are synthetic structured observations, not real classroom recordings.
- Wall-clock values include Python interpreter noise on a shared workstation.
- Token counts and cost are zero because no paid provider is invoked.
- tracemalloc peak is an in-process allocation high-water mark, not process RSS.
