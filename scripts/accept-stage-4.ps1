param(
    [switch]$RunLocalQwen,
    [string]$ModelPath = $env:LOCAL_QWEN_MODEL_PATH
)

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Python = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $Python)) { throw "Core .venv is missing" }

Set-Location $Root
& $Python -m ruff check .
if ($LASTEXITCODE -ne 0) { throw "Ruff failed" }
& $Python -m pytest -q
if ($LASTEXITCODE -ne 0) { throw "Offline phase-4 suite failed" }
& $Python -m pytest tests\unit\persistence\test_migrations.py -q
if ($LASTEXITCODE -ne 0) { throw "Phase-4 reversible migration acceptance failed" }
& $Python -m pip check
if ($LASTEXITCODE -ne 0) { throw "Installed dependency consistency check failed" }

if ($RunLocalQwen) {
    $QwenPython = Join-Path $Root ".qwen-runtime\Scripts\python.exe"
    if (-not (Test-Path -LiteralPath $QwenPython)) {
        throw "Run scripts\setup-local-qwen.ps1 before local-Qwen acceptance"
    }
    if (-not $ModelPath) {
        throw "Set LOCAL_QWEN_MODEL_PATH or pass -ModelPath with the local Qwen3.5 checkpoint path"
    }
    $env:RUN_LOCAL_QWEN_TESTS = "1"
    $env:LOCAL_QWEN_MODEL_PATH = [System.IO.Path]::GetFullPath($ModelPath)
    $env:LOCAL_QWEN_EVAL_OUTPUT = Join-Path $Root "runs\qwen35-temporary-stage4"
    & $QwenPython -m pytest tests\integration\test_local_qwen_smoke.py -q
    if ($LASTEXITCODE -ne 0) { throw "Temporary local-Qwen acceptance failed" }
    Write-Output "local_qwen_temporary_functional_acceptance=passed"
} else {
    Write-Output "local_qwen_temporary_functional_acceptance=not_requested"
}

Write-Output "stage4_offline_acceptance=passed"
