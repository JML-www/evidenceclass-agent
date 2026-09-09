$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $ProjectRoot
$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $Python)) { $Python = "python" }

& $Python -m ruff check evals packages tests
if ($LASTEXITCODE -ne 0) { throw "ruff failed" }
& $Python -m pytest -q tests/unit tests/integration
if ($LASTEXITCODE -ne 0) { throw "pytest failed" }
$env:PYTHONPATH = $ProjectRoot
& $Python -m evals.run_stage11_eval --output-dir (Join-Path $ProjectRoot "runs/stage-11")
if ($LASTEXITCODE -ne 0) { throw "stage 11 evaluator failed" }

$Report = Get-Content -Raw -LiteralPath (Join-Path $ProjectRoot "runs/stage-11/stage-11-report.json") | ConvertFrom-Json
if ($Report.perception.vision.trial_count -lt 30) { throw "vision fixture count is below 30" }
if ($Report.retrieval.dataset_size -ne 40) { throw "retrieval fixture count is not 40" }
if ($Report.agent.dataset_size -ne 50) { throw "agent fixture count is not 50" }
if ($Report.retrieval.workspace_leak_rate -ne 0) { throw "workspace leakage detected" }
if ($Report.agent.forbidden_tool_rate -ne 0) { throw "forbidden tool selected" }
Write-Host "Stage 11 acceptance passed: offline evaluators, schema tests, and report generated."
