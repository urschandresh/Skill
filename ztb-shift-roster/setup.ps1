#Requires -Version 5.1
<#
.SYNOPSIS
    One-time setup of ZTB ShiftOrbit on Windows (local only).

.DESCRIPTION
    Checks Python 3.11+ and Node.js 20+, creates backend\.venv, installs Python packages,
    installs frontend packages and builds the web UI. Nothing is uploaded anywhere; package
    downloads come from PyPI and the npm registry.

.PARAMETER Dev
    Also install test tools (pytest, Playwright test runner).

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\setup.ps1
#>
[CmdletBinding()]
param(
    [switch]$Dev
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$Root = $PSScriptRoot
$Backend = Join-Path $Root 'backend'
$Frontend = Join-Path $Root 'frontend'
$Venv = Join-Path $Backend '.venv'
$VenvPython = Join-Path $Venv 'Scripts\python.exe'

function Write-Step([string]$Message) { Write-Host "==> $Message" -ForegroundColor Cyan }

function Invoke-Native {
    param([string]$File, [string[]]$Arguments, [string]$What)
    & $File @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$What failed (exit code $LASTEXITCODE)." }
}

function Get-PythonVersion([string]$File, [string[]]$Prefix) {
    try {
        # No double quotes inside the code: Windows PowerShell 5.1 strips them from native arguments.
        $out = & $File @Prefix -c 'import sys; print(str(sys.version_info[0]) + chr(46) + str(sys.version_info[1]))' 2>$null
        if ($LASTEXITCODE -eq 0 -and $out) { return [version]($out | Select-Object -First 1) }
    } catch { }
    return $null
}

function Find-Python {
    # Prefer the Windows "py" launcher with an explicit version, then python on PATH.
    $candidates = @(
        @{ File = 'py'; Prefix = @('-3.12') },
        @{ File = 'py'; Prefix = @('-3.11') },
        @{ File = 'py'; Prefix = @('-3.13') },
        @{ File = 'python'; Prefix = @() }
    )
    foreach ($c in $candidates) {
        if (-not (Get-Command $c.File -ErrorAction SilentlyContinue)) { continue }
        $v = Get-PythonVersion $c.File $c.Prefix
        if ($v -and $v -ge [version]'3.11') { return $c }
    }
    return $null
}

Write-Host 'ZTB ShiftOrbit setup (local-only installation)' -ForegroundColor White

Write-Step 'Checking Python 3.11 or newer'
$py = Find-Python
if (-not $py) {
    throw 'Python 3.11+ not found. Install it from https://www.python.org/downloads/windows/ (tick "Add python.exe to PATH") and run setup again.'
}
$pyVersion = Get-PythonVersion $py.File $py.Prefix
Write-Host "    Using $($py.File) $($py.Prefix -join ' ') (Python $pyVersion)"

Write-Step 'Checking Node.js 20 or newer'
if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
    throw 'Node.js not found. Install the LTS version from https://nodejs.org/ and run setup again.'
}
$nodeVersion = [version]((& node --version).TrimStart('v'))
if ($nodeVersion -lt [version]'20.0') { throw "Node.js $nodeVersion is too old; install Node.js 20 or newer." }
Write-Host "    Node.js $nodeVersion"
$npm = (Get-Command npm.cmd -ErrorAction SilentlyContinue)
if (-not $npm) { throw 'npm was not found next to Node.js.' }

Write-Step 'Creating Python virtual environment (backend\.venv)'
if (-not (Test-Path $VenvPython)) {
    Invoke-Native $py.File ($py.Prefix + @('-m', 'venv', $Venv)) 'Creating the virtual environment'
}

Write-Step 'Installing Python packages'
Invoke-Native $VenvPython @('-m', 'pip', 'install', '--disable-pip-version-check', '--upgrade', 'pip') 'Upgrading pip'
$req = if ($Dev) { 'requirements-dev.txt' } else { 'requirements.txt' }
Invoke-Native $VenvPython @('-m', 'pip', 'install', '--disable-pip-version-check', '-r', (Join-Path $Backend $req)) 'Installing Python packages'

Write-Step 'Installing frontend packages'
Push-Location $Frontend
try {
    Invoke-Native $npm.Source @('ci', '--no-audit', '--no-fund') 'npm ci'
    Write-Step 'Building the web interface'
    Invoke-Native $npm.Source @('run', 'build') 'Building the frontend'
} finally {
    Pop-Location
}

Write-Step 'Preparing the local data folder'
$data = Join-Path $Root 'data'
New-Item -ItemType Directory -Force -Path $data | Out-Null

Write-Step 'Checking the installation'
Invoke-Native $VenvPython @('-c', 'import ortools, fastapi, sqlalchemy, openpyxl, tzdata; print(ortools.__version__)') 'Import check'

Write-Host ''
Write-Host 'Setup complete.' -ForegroundColor Green
Write-Host "Data will be stored in: $data"
Write-Host 'Start the app with:   powershell -ExecutionPolicy Bypass -File .\start.ps1'
Write-Host 'Stop it with:         powershell -ExecutionPolicy Bypass -File .\stop.ps1'
