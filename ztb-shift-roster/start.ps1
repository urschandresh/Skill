#Requires -Version 5.1
<#
.SYNOPSIS
    Start ZTB ShiftOrbit on this computer only (http://127.0.0.1:8000).

.PARAMETER Port
    Backend port (default 8000). Always bound to 127.0.0.1.

.PARAMETER Dev
    Also start the Vite development server on http://127.0.0.1:5173 (for developers).

.PARAMETER NoBrowser
    Do not open the browser.
#>
[CmdletBinding()]
param(
    [ValidateRange(1024, 65535)][int]$Port = 8000,
    [switch]$Dev,
    [switch]$NoBrowser
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$Root = $PSScriptRoot
$Backend = Join-Path $Root 'backend'
$Frontend = Join-Path $Root 'frontend'
$RunDir = Join-Path $Root '.run'
$VenvPython = Join-Path $Backend '.venv\Scripts\python.exe'
$BackendPid = Join-Path $RunDir 'backend.pid'
$FrontendPid = Join-Path $RunDir 'frontend.pid'

function Test-Running([string]$PidFile) {
    if (-not (Test-Path $PidFile)) { return $false }
    $procId = [int](Get-Content $PidFile -Raw).Trim()
    return [bool](Get-Process -Id $procId -ErrorAction SilentlyContinue)
}

function Test-PortInUse([int]$P) {
    $listeners = [System.Net.NetworkInformation.IPGlobalProperties]::GetIPGlobalProperties().GetActiveTcpListeners()
    return [bool]($listeners | Where-Object { $_.Port -eq $P })
}

if (-not (Test-Path $VenvPython)) { throw 'Not set up yet. Run .\setup.ps1 first.' }
if (-not $Dev -and -not (Test-Path (Join-Path $Frontend 'dist\index.html'))) {
    throw 'The web interface is not built. Run .\setup.ps1 (or "npm run build" in frontend).'
}
New-Item -ItemType Directory -Force -Path $RunDir | Out-Null

if (Test-Running $BackendPid) {
    Write-Host 'ShiftOrbit is already running.' -ForegroundColor Yellow
} else {
    if (Test-PortInUse $Port) { throw "Port $Port is already in use. Stop the other program or use -Port 8001." }
    # Child processes inherit these. The backend refuses to bind to anything but loopback.
    $env:ZTB_HOST = '127.0.0.1'
    $env:ZTB_PORT = "$Port"
    $proc = Start-Process -FilePath $VenvPython -ArgumentList 'run.py' -WorkingDirectory $Backend `
        -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput (Join-Path $RunDir 'backend.log') -RedirectStandardError (Join-Path $RunDir 'backend.err.log')
    Set-Content -Path $BackendPid -Value $proc.Id -Encoding ascii

    Write-Host "Starting ShiftOrbit backend (PID $($proc.Id))..."
    $healthy = $false
    for ($i = 0; $i -lt 60; $i++) {
        Start-Sleep -Seconds 1
        if ($proc.HasExited) { break }
        try {
            $h = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/health" -TimeoutSec 2
            if ($h.status -eq 'ok') { $healthy = $true; break }
        } catch { }
    }
    if (-not $healthy) {
        Write-Host "Backend did not start. Last log lines:" -ForegroundColor Red
        Get-Content (Join-Path $RunDir 'backend.err.log') -Tail 20 -ErrorAction SilentlyContinue
        throw 'Startup failed.'
    }
}

$url = "http://127.0.0.1:$Port"
if ($Dev) {
    if (-not (Test-Running $FrontendPid)) {
        $env:ZTB_BACKEND_URL = $url
        $npm = (Get-Command npm.cmd).Source
        $fe = Start-Process -FilePath $npm -ArgumentList 'run', 'dev' -WorkingDirectory $Frontend -WindowStyle Hidden -PassThru `
            -RedirectStandardOutput (Join-Path $RunDir 'frontend.log') -RedirectStandardError (Join-Path $RunDir 'frontend.err.log')
        Set-Content -Path $FrontendPid -Value $fe.Id -Encoding ascii
        Start-Sleep -Seconds 3
    }
    $url = 'http://127.0.0.1:5173'
}

Write-Host "ZTB ShiftOrbit is running at $url (this computer only)." -ForegroundColor Green
Write-Host 'Stop it with: powershell -ExecutionPolicy Bypass -File .\stop.ps1'
if (-not $NoBrowser) { Start-Process $url }
