param(
    [switch]$RunFull,
    [string]$Python = ".\.venv\Scripts\python.exe"
)

$ErrorActionPreference = "Stop"
if (-not (Test-Path -LiteralPath $Python)) { $Python = "python" }

Write-Host "[stage7] Ruff"
& $Python -m ruff check .

Write-Host "[stage7] focused runtime tests"
& $Python -m pytest tests\unit\agent_runtime tests\unit\persistence\test_migrations.py -q

Write-Host "[stage7] dependency consistency"
& $Python -m pip check

if ($RunFull) {
    Write-Host "[stage7] full regression"
    & $Python -m pytest -q
}

Write-Host "[stage7] compileall"
& $Python -m compileall -q packages tests
Write-Host "stage 7 acceptance passed"
