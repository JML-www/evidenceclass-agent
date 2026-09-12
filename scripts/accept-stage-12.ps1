$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $ProjectRoot
$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $Python)) { $Python = "python" }

Write-Host "[stage12] ruff"
& $Python -m ruff check packages apps tests evals
if ($LASTEXITCODE -ne 0) { throw "ruff failed" }

Write-Host "[stage12] pytest (unit + integration)"
& $Python -m pytest -q tests/unit tests/integration
if ($LASTEXITCODE -ne 0) { throw "pytest failed" }

$env:PYTHONPATH = $ProjectRoot

Write-Host "[stage12] fault injection"
$IncidentReport = Join-Path $ProjectRoot "docs/incidents/fault-injection-001.md"
& $Python -m evals.run_stage12_faults --report $IncidentReport
if ($LASTEXITCODE -ne 0) { throw "fault-injection gate failed" }
if (-not (Test-Path -LiteralPath $IncidentReport)) { throw "fault-injection report missing" }

Write-Host "[stage12] queue-protection load probe"
& $Python -m evals.run_stage12_load --output (Join-Path $ProjectRoot "runs/stage-12/queue-load.json")
if ($LASTEXITCODE -ne 0) { throw "queue-protection probe failed" }

Write-Host "[stage12] performance baseline"
& $Python -m evals.run_stage12_benchmark --output-dir (Join-Path $ProjectRoot "evals/reports")
if ($LASTEXITCODE -ne 0) { throw "benchmark failed" }
$Benchmark = Join-Path $ProjectRoot "evals/reports/benchmark-v0.12.0.md"
if (-not (Test-Path -LiteralPath $Benchmark)) { throw "benchmark report missing" }

# The metrics endpoint and the headless panel must expose the stage timings of
# one real run, not just an empty registry.
Write-Host "[stage12] operations-panel probe"
& $Python -m evals.run_stage12_panel --output (Join-Path $ProjectRoot "runs/stage-12/panel.json")
if ($LASTEXITCODE -ne 0) { throw "operations-panel probe failed" }

Write-Host "Stage 12 acceptance passed: structured logs, unified correlation ids, metrics, 10 fault injections, queue backpressure and the offline benchmark are all green."
