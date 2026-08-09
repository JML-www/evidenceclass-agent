param(
    [string]$ModelPath = $env:LOCAL_QWEN_MODEL_PATH,
    [string]$RuntimePath = "",
    [string]$TorchIndexUrl = "https://download.pytorch.org/whl/cu126"
)

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
if (-not $RuntimePath) { $RuntimePath = Join-Path $Root ".qwen-runtime" }
$RuntimePath = [System.IO.Path]::GetFullPath($RuntimePath)
if (-not $ModelPath) {
    throw "Set LOCAL_QWEN_MODEL_PATH or pass -ModelPath with the local Qwen3.5 checkpoint path"
}
$ModelPath = [System.IO.Path]::GetFullPath($ModelPath)

if (-not (Test-Path -LiteralPath (Join-Path $ModelPath "config.json"))) {
    throw "Qwen model config was not found: $ModelPath"
}
$config = Get-Content -LiteralPath (Join-Path $ModelPath "config.json") -Raw -Encoding utf8
if ($config -notmatch 'Qwen3_5ForConditionalGeneration' -or $config -notmatch 'vision_config') {
    throw "The selected checkpoint is not the expected multimodal Qwen3.5 model."
}

if (-not (Test-Path -LiteralPath (Join-Path $RuntimePath "Scripts\python.exe"))) {
    py -3.10 -m venv $RuntimePath
    if ($LASTEXITCODE -ne 0) { throw "Could not create the isolated Qwen runtime" }
}
$Python = Join-Path $RuntimePath "Scripts\python.exe"

& $Python -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw "pip upgrade failed" }
& $Python -m pip install torch==2.7.1 torchvision==0.22.1 --index-url $TorchIndexUrl
if ($LASTEXITCODE -ne 0) { throw "GPU PyTorch installation failed" }
& $Python -m pip install -e "${Root}[dev,local-qwen]"
if ($LASTEXITCODE -ne 0) { throw "EvidenceClass local-Qwen dependencies failed" }

& $Python -c "import torch, transformers; assert torch.cuda.is_available(); assert hasattr(transformers, 'Qwen3_5ForConditionalGeneration'); print('local_qwen_runtime=ready')"
if ($LASTEXITCODE -ne 0) { throw "CUDA or Qwen3.5 runtime probe failed" }

Write-Output "The local Qwen runtime is ready. It is a temporary phase-4 functional model."
Write-Output "No final model selection or accuracy claim is implied."
