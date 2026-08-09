$ErrorActionPreference = "Stop"

$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$ComposeFile = Join-Path $Root "deploy\docker-compose.yml"
$EnvFile = Join-Path $Root ".env"
$Python = Join-Path $Root ".venv\Scripts\python.exe"

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "Docker CLI was not found. Install and start Docker Desktop before infrastructure acceptance."
}
if (-not (Test-Path -LiteralPath $EnvFile)) {
    throw "Create .env from .env.example and replace every placeholder before acceptance."
}
if (-not (Test-Path -LiteralPath $Python)) {
    throw "The repository .venv is missing. Create it and install -e `".[dev]`" first."
}

foreach ($line in Get-Content -LiteralPath $EnvFile -Encoding utf8) {
    $trimmed = $line.Trim()
    if (-not $trimmed -or $trimmed.StartsWith("#")) { continue }
    $parts = $trimmed.Split("=", 2)
    if ($parts.Count -eq 2) {
        [Environment]::SetEnvironmentVariable($parts[0], $parts[1], "Process")
    }
}

function Invoke-Compose {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments)
    & docker compose --env-file $EnvFile -f $ComposeFile @Arguments
    if ($LASTEXITCODE -ne 0) { throw "docker compose failed: $Arguments" }
}

function Wait-Healthy {
    $services = @("postgres", "redis", "minio")
    foreach ($attempt in 1..60) {
        $allHealthy = $true
        foreach ($service in $services) {
            $containerId = (& docker compose --env-file $EnvFile -f $ComposeFile ps -q $service).Trim()
            if (-not $containerId) { $allHealthy = $false; continue }
            $health = (& docker inspect --format "{{.State.Health.Status}}" $containerId).Trim()
            if ($health -ne "healthy") { $allHealthy = $false }
        }
        if ($allHealthy) { return }
        Start-Sleep -Seconds 2
    }
    Invoke-Compose -Arguments @("ps")
    throw "PostgreSQL, Redis, and MinIO did not all become healthy."
}

Set-Location $Root
Invoke-Compose -Arguments @("up", "-d", "postgres", "redis", "minio")
Wait-Healthy

& $Python -m alembic upgrade head
if ($LASTEXITCODE -ne 0) { throw "Alembic upgrade failed" }
& $Python -m alembic downgrade -1
if ($LASTEXITCODE -ne 0) { throw "Alembic downgrade failed" }
& $Python -m alembic upgrade head
if ($LASTEXITCODE -ne 0) { throw "Alembic second upgrade failed" }

$token = [Guid]::NewGuid().ToString("N")
& $Python scripts\stage3_infrastructure_probe.py write $token
if ($LASTEXITCODE -ne 0) { throw "Persistence sentinel write failed" }

Invoke-Compose -Arguments @("restart", "postgres", "redis", "minio")
Wait-Healthy
& $Python scripts\stage3_infrastructure_probe.py verify $token
if ($LASTEXITCODE -ne 0) { throw "A data volume lost its persistence sentinel" }

$env:RUN_STAGE3_INFRA_TESTS = "1"
& $Python -m pytest tests\integration\test_stage3_infrastructure.py -q
if ($LASTEXITCODE -ne 0) { throw "Stage-3 integration test failed" }

Write-Output "stage3_infrastructure_acceptance=passed"
Write-Output "Containers remain running and named volumes remain intact for inspection."
