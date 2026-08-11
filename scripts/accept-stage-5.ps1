param(
    [switch]$RunRealMediaModels,
    [string]$WhisperModel = $env:FASTER_WHISPER_MODEL,
    [string]$HfEndpoint = $env:HF_ENDPOINT
)

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Python = Join-Path $Root ".venv\Scripts\python.exe"
$Ffmpeg = Join-Path $Root ".media-runtime\bin\ffmpeg.exe"
$Ffprobe = Join-Path $Root ".media-runtime\bin\ffprobe.exe"
if (-not (Test-Path -LiteralPath $Python)) { throw "Core .venv is missing" }
if (-not (Test-Path -LiteralPath $Ffmpeg) -or -not (Test-Path -LiteralPath $Ffprobe)) {
    throw "Run scripts\setup-media-tools.ps1 before phase-5 acceptance"
}

$env:EVIDENCECLASS_FFMPEG_PATH = $Ffmpeg
$env:EVIDENCECLASS_FFPROBE_PATH = $Ffprobe
Set-Location $Root

& $Python -m ruff check .
if ($LASTEXITCODE -ne 0) { throw "Ruff failed" }
& $Python -m pytest tests\unit\media tests\integration\test_stage5_media_pipeline.py -q
if ($LASTEXITCODE -ne 0) { throw "Phase-5 media acceptance failed" }
& $Python -m pytest -q
if ($LASTEXITCODE -ne 0) { throw "Full regression suite failed" }
& $Python -m pip check
if ($LASTEXITCODE -ne 0) { throw "Installed dependency consistency check failed" }

if ($RunRealMediaModels) {
    if (-not $WhisperModel) {
        throw "Set FASTER_WHISPER_MODEL or pass -WhisperModel for opt-in real-model acceptance"
    }
    $env:RUN_STAGE5_REAL_MEDIA_MODELS = "1"
    $env:FASTER_WHISPER_MODEL = $WhisperModel
    $env:HF_HOME = Join-Path $Root ".media-runtime\huggingface"
    $env:HF_HUB_DISABLE_XET = "1"
    $env:HF_HUB_DISABLE_SYMLINKS_WARNING = "1"
    if ($HfEndpoint) { $env:HF_ENDPOINT = $HfEndpoint }
    & $Python evals\media\run_real_media_eval.py `
        --output runs\stage5-real-media-eval `
        --whisper-model $WhisperModel
    if ($LASTEXITCODE -ne 0) { throw "Real ASR/OCR phase-5 acceptance failed" }
    Write-Output "stage5_real_media_model_acceptance=passed"
} else {
    Write-Output "stage5_real_media_model_acceptance=not_requested"
}

Write-Output "stage5_offline_acceptance=passed"
