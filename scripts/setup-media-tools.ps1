param(
    [switch]$Force
)

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Runtime = Join-Path $Root ".media-runtime"
$Bin = Join-Path $Runtime "bin"
$Cache = Join-Path $Runtime "npm-cache"
New-Item -ItemType Directory -Force -Path $Bin, $Cache | Out-Null

function Install-NpmBinary {
    param(
        [Parameter(Mandatory = $true)][string]$Package,
        [Parameter(Mandatory = $true)][string]$Binary
    )
    $Target = Join-Path $Bin $Binary
    if ((Test-Path -LiteralPath $Target) -and -not $Force) { return }
    if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
        throw "npm is required to bootstrap project-local media tools"
    }
    $PackJson = & npm pack $Package --json --pack-destination $Cache
    if ($LASTEXITCODE -ne 0) { throw "npm could not download $Package" }
    $Pack = $PackJson | ConvertFrom-Json
    $Archive = Join-Path $Cache $Pack[0].filename
    $Extract = Join-Path $Cache ([System.IO.Path]::GetFileNameWithoutExtension($Binary))
    New-Item -ItemType Directory -Force -Path $Extract | Out-Null
    & tar -xzf $Archive -C $Extract
    if ($LASTEXITCODE -ne 0) { throw "could not extract $Package" }
    $Source = Get-ChildItem -LiteralPath $Extract -Recurse -File -Filter $Binary |
        Select-Object -First 1
    if (-not $Source) { throw "$Binary was absent from $Package" }
    Copy-Item -LiteralPath $Source.FullName -Destination $Target -Force
}

Install-NpmBinary -Package "@ffmpeg-installer/win32-x64@4.1.0" -Binary "ffmpeg.exe"
Install-NpmBinary -Package "@ffprobe-installer/win32-x64@5.1.0" -Binary "ffprobe.exe"

$Ffmpeg = Join-Path $Bin "ffmpeg.exe"
$Ffprobe = Join-Path $Bin "ffprobe.exe"
& $Ffmpeg -version | Select-Object -First 1
if ($LASTEXITCODE -ne 0) { throw "project-local ffmpeg verification failed" }
& $Ffprobe -version | Select-Object -First 1
if ($LASTEXITCODE -ne 0) { throw "project-local ffprobe verification failed" }

Write-Output "media_tools_ready=true"
Write-Output "media_runtime=$Runtime"
