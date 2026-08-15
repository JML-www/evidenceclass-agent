param(
    [switch]$RunPgVector
)

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Python = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $Python)) { throw "Core .venv is missing" }

Set-Location $Root
& $Python -m ruff check .
if ($LASTEXITCODE -ne 0) { throw "Ruff failed" }
& $Python evals\retrieval\run_stage6_eval.py --output runs\stage6-retrieval-eval
if ($LASTEXITCODE -ne 0) { throw "Phase-6 retrieval evaluation failed" }
& $Python -m pytest tests\unit\retrieval tests\integration\test_stage6_retrieval.py -q
if ($LASTEXITCODE -ne 0) { throw "Phase-6 focused acceptance failed" }
& $Python -m pytest -q
if ($LASTEXITCODE -ne 0) { throw "Full regression suite failed" }
& $Python -m pip check
if ($LASTEXITCODE -ne 0) { throw "Installed dependency consistency check failed" }

if ($RunPgVector) {
    if (-not $env:DATABASE_URL) { throw "Set DATABASE_URL before live pgvector acceptance" }
    $env:RUN_STAGE6_PGVECTOR_TESTS = "1"
    & $Python -m pytest tests\integration\test_stage6_pgvector.py -q
    if ($LASTEXITCODE -ne 0) { throw "Live pgvector acceptance failed" }
    Write-Output "stage6_live_pgvector_acceptance=passed"
} else {
    Write-Output "stage6_live_pgvector_acceptance=not_requested"
}

Write-Output "stage6_offline_acceptance=passed"
