param(
    [switch]$RunFull,
    [switch]$RunCelery,
    [string]$Python = ".\.venv\Scripts\python.exe"
)

$ErrorActionPreference = "Stop"
if (-not (Test-Path -LiteralPath $Python)) { $Python = "python" }

function Invoke-Checked {
    param(
        [Parameter(Mandatory = $true)]
        [scriptblock]$Command,
        [Parameter(Mandatory = $true)]
        [string]$Description
    )

    & $Command
    if ($LASTEXITCODE -ne 0) {
        throw "$Description failed with exit code $LASTEXITCODE"
    }
}

Write-Host "[stage8] Ruff"
Invoke-Checked { & $Python -m ruff check . } "Ruff"

Write-Host "[stage8] API, Worker, Outbox, SSE, cancellation, and migration tests"
Invoke-Checked {
    & $Python -m pytest `
    tests\unit\api `
    tests\unit\worker `
    tests\unit\persistence\test_stage8_outbox.py `
    tests\unit\persistence\test_migrations.py `
    -q
} "Stage-8 focused tests"

Write-Host "[stage8] dependency consistency"
Invoke-Checked { & $Python -m pip check } "pip check"

if ($RunCelery) {
    Write-Host "[stage8] live PostgreSQL/Redis Celery integration"
    $env:RUN_STAGE8_CELERY_TESTS = "1"
    Invoke-Checked {
        & $Python -m pytest tests\integration\test_stage8_celery.py -q
    } "Stage-8 Celery integration tests"
}

if ($RunFull) {
    Write-Host "[stage8] full regression"
    Invoke-Checked { & $Python -m pytest -q } "Full regression tests"
}

Write-Host "[stage8] compileall"
Invoke-Checked { & $Python -m compileall -q apps packages tests } "compileall"
Write-Host "stage 8 acceptance passed"
