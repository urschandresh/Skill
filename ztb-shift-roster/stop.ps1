#Requires -Version 5.1
<#
.SYNOPSIS
    Stop ZTB ShiftOrbit processes started by start.ps1.
#>
[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$RunDir = Join-Path $PSScriptRoot '.run'
$stopped = 0

foreach ($name in @('frontend', 'backend')) {
    $pidFile = Join-Path $RunDir "$name.pid"
    if (-not (Test-Path $pidFile)) { continue }
    $procId = [int](Get-Content $pidFile -Raw).Trim()
    if (Get-Process -Id $procId -ErrorAction SilentlyContinue) {
        # /T also stops child processes (npm starts node; Python may start solver threads only).
        & taskkill.exe /PID $procId /T /F | Out-Null
        Write-Host "Stopped $name (PID $procId)."
        $stopped++
    }
    Remove-Item $pidFile -Force
}

if ($stopped -eq 0) {
    Write-Host 'ShiftOrbit was not running (no process started by start.ps1 found).' -ForegroundColor Yellow
} else {
    Write-Host 'ZTB ShiftOrbit stopped. Your data remains in the data folder.' -ForegroundColor Green
}
