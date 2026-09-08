# Media Host 1.6 — Windows click-and-run bootstrap.
# Finds Python, or downloads the official embeddable build, then opens the setup page.

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

function Find-Repo {
    if (Test-Path (Join-Path $Root "..\agent.py")) {
        return (Resolve-Path (Join-Path $Root "..")).Path
    }
    if (Test-Path (Join-Path $Root "agent.py")) { return $Root }
    return (Resolve-Path (Join-Path $Root "..")).Path
}

$Repo = Find-Repo
$Runtime = Join-Path $Root "runtime\python"
$Embedded = Join-Path $Runtime "python.exe"

function Find-SystemPython {
    foreach ($cmd in @("py", "python", "python3")) {
        $p = Get-Command $cmd -ErrorAction SilentlyContinue
        if (-not $p) { continue }
        try {
            $ver = & $p.Source -c "import sys; print('%d.%d' % sys.version_info[:2])" 2>$null
            if ($ver -and [version]$ver -ge [version]"3.9") {
                return $p.Source
            }
        } catch { }
    }
    return $null
}

function Install-EmbeddedPython {
    New-Item -ItemType Directory -Force -Path $Runtime | Out-Null
    $zip = Join-Path $env:TEMP "python-embed-mediahost.zip"
    $url = "https://www.python.org/ftp/python/3.12.10/python-3.12.10-embed-amd64.zip"
    Write-Host "Downloading official Python 3.12 embeddable (no full installer)..."
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    Invoke-WebRequest -Uri $url -OutFile $zip -UseBasicParsing
    Expand-Archive -Path $zip -DestinationPath $Runtime -Force
    Remove-Item $zip -ErrorAction SilentlyContinue
    $pth = Get-ChildItem $Runtime -Filter "python*._pth" | Select-Object -First 1
    if ($pth) {
        @(
            "python312.zip"
            "."
            $Root
            $Repo
            "import site"
        ) | Set-Content -Path $pth.FullName -Encoding ASCII
    }
}

$Py = Find-SystemPython
if (-not $Py) {
    if (-not (Test-Path $Embedded)) {
        Install-EmbeddedPython
    }
    $Py = $Embedded
}

if (-not (Test-Path $Py)) {
    Write-Host "Could not find or install Python. Install 3.9+ from python.org (tick Add to PATH) and run again."
    exit 1
}

Write-Host "Using $Py"
Write-Host "Opening Media Host setup in your browser..."
& $Py (Join-Path $Root "wizard.py")
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
