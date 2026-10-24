#Requires -Version 5.1
<#
.SYNOPSIS
    One-step installer for ZTB ShiftOrbit on Windows: prerequisites, download, setup, start.

.DESCRIPTION
    1. Checks for Python 3.11+ and Node.js 20+. If missing, offers to install them with winget
       (asks before installing anything).
    2. Downloads ShiftOrbit from GitHub into a folder you choose (default: Documents\ZTB-ShiftOrbit).
    3. Runs setup.ps1 and then start.ps1, which opens http://127.0.0.1:8000.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\install.ps1
#>
[CmdletBinding()]
param(
    [string]$InstallDir = (Join-Path ([Environment]::GetFolderPath('MyDocuments')) 'ZTB-ShiftOrbit'),
    [string]$Branch = 'ccr-fa255194-qgmtwb'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$Repo = 'urschandresh/Skill'

function Write-Step([string]$Message) { Write-Host "==> $Message" -ForegroundColor Cyan }

function Refresh-Path {
    $machine = [Environment]::GetEnvironmentVariable('Path', 'Machine')
    $user = [Environment]::GetEnvironmentVariable('Path', 'User')
    $env:Path = "$machine;$user"
}

function Test-Python {
    foreach ($c in @(@('py', '-3.12'), @('py', '-3.11'), @('py', '-3.13'), @('python'))) {
        if (-not (Get-Command $c[0] -ErrorAction SilentlyContinue)) { continue }
        try {
            $args2 = @($c | Select-Object -Skip 1) + @('-c', 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)')
            & $c[0] @args2 2>$null
            if ($LASTEXITCODE -eq 0) { return $true }
        } catch { }
    }
    return $false
}

function Test-Node {
    if (-not (Get-Command node -ErrorAction SilentlyContinue)) { return $false }
    $v = [version]((& node --version).TrimStart('v'))
    return $v -ge [version]'20.0'
}

function Install-WithWinget([string]$Id, [string]$Label) {
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        throw "$Label is missing and winget is not available. Install $Label manually, then run this script again."
    }
    $answer = Read-Host "$Label is missing. Install it now with winget ($Id)? [Y/n]"
    if ($answer -and $answer.Trim().ToLower() -notin @('y', 'yes')) { throw "$Label is required. Install it and run again." }
    & winget install --id $Id --exact --accept-package-agreements --accept-source-agreements
    if ($LASTEXITCODE -ne 0) { throw "winget could not install $Label (exit code $LASTEXITCODE)." }
    Refresh-Path
}

Write-Host 'ZTB ShiftOrbit installer (runs on this computer only)' -ForegroundColor White

Write-Step 'Checking Python 3.11+'
if (-not (Test-Python)) { Install-WithWinget 'Python.Python.3.12' 'Python 3.12' }
if (-not (Test-Python)) { throw 'Python was installed but is not on PATH yet. Close this window, open a new PowerShell and run the installer again.' }

Write-Step 'Checking Node.js 20+'
if (-not (Test-Node)) { Install-WithWinget 'OpenJS.NodeJS.LTS' 'Node.js LTS' }
if (-not (Test-Node)) { throw 'Node.js was installed but is not on PATH yet. Close this window, open a new PowerShell and run the installer again.' }

$AppDir = Join-Path $InstallDir 'ztb-shift-roster'
if (Test-Path (Join-Path $AppDir 'setup.ps1')) {
    Write-Step "ShiftOrbit already present in $AppDir (delete that folder to download a fresh copy)"
} else {
    Write-Step "Downloading ShiftOrbit (branch $Branch)"
    $zip = Join-Path $env:TEMP "ztb-shiftorbit-$([guid]::NewGuid().ToString('N')).zip"
    $extract = Join-Path $env:TEMP "ztb-shiftorbit-$([guid]::NewGuid().ToString('N'))"
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    Invoke-WebRequest -UseBasicParsing -Uri "https://github.com/$Repo/archive/refs/heads/$Branch.zip" -OutFile $zip
    Expand-Archive -Path $zip -DestinationPath $extract -Force
    $source = Get-ChildItem $extract -Directory | Select-Object -First 1
    New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
    Copy-Item -Path (Join-Path $source.FullName 'ztb-shift-roster') -Destination $InstallDir -Recurse -Force
    Remove-Item $zip -Force
    Remove-Item $extract -Recurse -Force
    Write-Host "    Installed to $AppDir"
}

Write-Step 'Running setup (Python packages, web interface build)'
& powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $AppDir 'setup.ps1')
if ($LASTEXITCODE -ne 0) { throw 'Setup failed; see the messages above.' }

Write-Step 'Starting ShiftOrbit'
& powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $AppDir 'start.ps1')
if ($LASTEXITCODE -ne 0) { throw 'Start failed; see the messages above.' }

Write-Host ''
Write-Host "Done. ShiftOrbit lives in $AppDir" -ForegroundColor Green
Write-Host "Next time: open PowerShell in that folder and run  powershell -ExecutionPolicy Bypass -File .\start.ps1"
