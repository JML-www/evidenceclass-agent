# Local infrastructure

One compose project backs the infrastructure acceptance (phase 3) and the phase-12
observability stack.

```bash
cd deploy
cp ../.env.example ../.env      # then fill in every value
docker compose up -d
docker compose ps
```

| service | port | purpose |
| --- | --- | --- |
| `postgres` | 5432 | pgvector-enabled PostgreSQL: durable jobs, runs, events, outbox, checkpoints |
| `redis` | 6379 | Celery broker and result backend |
| `minio` | 9000 / 9001 | S3-compatible object storage for media and artifacts |
| `prometheus` | 9090 | scrapes the API `/metrics` endpoint |
| `grafana` | 3000 | provisions the EvidenceClass dashboard |

## Object storage image

Upstream MinIO stopped publishing community container images in October 2025. The compose
file therefore pins `pgsty/silo`, a maintained wire-compatible fork: identical `MINIO_*`
environment variables, identical `/minio/*` health routes, identical on-disk format, and the
same `server /data` entrypoint. Nothing in the application code or the acceptance scripts had
to change.

## Observability stack

The API is expected to run **on the host**, not inside this compose project. Prometheus
reaches it through `host.docker.internal:8000`, which Docker Desktop provides natively and
which the `prometheus` service maps explicitly via `extra_hosts` for Linux hosts.

Start the API with metrics enabled:

```bash
EVIDENCECLASS_METRICS_ENABLED=1 <python> -m uvicorn apps.api.main:app --host 0.0.0.0 --port 8000
```

Then:

1. Open Prometheus at http://127.0.0.1:9090 and confirm the `evidenceclass-api` target is `UP`
   under **Status → Targets**. If it is `DOWN`, the API is not reachable from the container —
   check the port and whether `EVIDENCECLASS_METRICS_ENABLED` is set.
2. Open Grafana at http://127.0.0.1:3000. The dashboard **EvidenceClass 可观测性** lives in the
   `EvidenceClass` folder and is provisioned from
   `deploy/grafana/dashboards/evidenceclass-observability.json`. Anonymous access is view-only;
   log in as `admin` with `GRAFANA_ADMIN_PASSWORD` to edit.
3. `EVIDENCECLASS_METRICS_ENABLED=0` makes `/metrics` return 404, which is the intended way to
   keep the endpoint closed in an environment that should not expose it.

### Dashboard panels and their sources

Every panel reads a metric that the application actually records. The mapping is:

| panel | metric |
| --- | --- |
| HTTP request rate by status | `evidenceclass_http_requests_total{method,route,status}` |
| HTTP latency p95 / p50 | `evidenceclass_http_request_milliseconds` (histogram) |
| HTTP 5xx ratio | `evidenceclass_http_requests_total{status=~"5.."}` |
| Agent run rate by outcome | `evidenceclass_agent_runs_total{outcome}` |
| End-to-end run time | `evidenceclass_agent_run_milliseconds{outcome}` |
| Average time per stage | `evidenceclass_stage_<stage>_milliseconds` |
| Queue in flight / weight | `evidenceclass_queue_in_flight`, `evidenceclass_queue_weight` |
| Admission rejections by code | `evidenceclass_queue_rejections_total{code}` |
| Worker active runs | `evidenceclass_worker_active` |
| Tool call rate / retry rate | `evidenceclass_tool_calls_total{tool,status}`, `evidenceclass_tool_retries_total{tool}` |
| Model tokens / cost / 429 / 5xx | `evidenceclass_model_tokens_total`, `evidenceclass_model_cost_total`, `evidenceclass_model_rate_limited_total`, `evidenceclass_model_server_errors_total` |
| Media realtime factor / peak memory | `evidenceclass_media_realtime_factor{media_kind}`, `evidenceclass_media_peak_memory_mb{media_kind}` |
| Review backlog / duration p95 | `evidenceclass_review_backlog`, `evidenceclass_review_duration_milliseconds` |
| Fault injections | `evidenceclass_fault_injections_total{fault,recovered}` |

Some panels read **zero** in the offline acceptance profile and that is expected, not a bug:

- Token, cost, 429, and 5xx series stay at zero because the deterministic fake adapter makes no
  provider call. They are wired so a real gateway only has to increment them.
- `evidenceclass_media_realtime_factor` and `_peak_memory_mb` are only written on a media run, so
  the panels are empty until one has executed.
- `evidenceclass_worker_active` is per process, so a multi-worker deployment shows one series per
  scraped process.
- `evidenceclass_fault_injections_total` only moves when the deterministic fault harness runs.

### Image pins

The Prometheus and Grafana tags are real published releases, but release tags are occasionally
yanked by upstream. Verify before bumping:

```bash
docker manifest inspect prom/prometheus:v2.53.0
docker manifest inspect grafana/grafana:11.1.0
```

## Environment variables added by this stack

| variable | default | meaning |
| --- | --- | --- |
| `PROMETHEUS_PORT` | 9090 | host port for the Prometheus UI |
| `GRAFANA_PORT` | 3000 | host port for the Grafana UI |
| `GRAFANA_ADMIN_PASSWORD` | required | Grafana admin password; must be set in `.env` |
| `GRAFANA_ADMIN_USER` | `admin` | Grafana admin user |
| `GRAFANA_ANONYMOUS_ENABLED` | `true` | view-only anonymous access; disable off localhost |
