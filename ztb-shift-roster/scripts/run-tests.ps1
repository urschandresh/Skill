#Requires -Version 5.1
# Run every automated test suite on Windows. Requires .\setup.ps1 -Dev first.
# Usage: powershell -ExecutionPolicy Bypass -File .\scripts\run-tests.ps1 [-SkipE2E]
[CmdletBinding()]
param([switch]$SkipE2E)
$ErrorActionPreference = 'Stop'
$Root = Split-Path $PSScriptRoot -Parent
$py = Join-Path $Root 'backend\.venv\Scripts\python.exe'
function Run([string]$Label, [scriptblock]$Block) {
    Write-Host "==> $Label" -ForegroundColor Cyan
    & $Block
    if ($LASTEXITCODE -ne 0) { throw "$Label failed" }
}
Push-Location (Join-Path $Root 'backend')
try { Run 'Backend tests (pytest)' { & $py -m pytest } } finally { Pop-Location }
Push-Location (Join-Path $Root 'frontend')
try {
    Run 'Type check' { & npm.cmd run typecheck }
    Run 'Frontend unit tests (Vitest)' { & npm.cmd test }
    if (-not $SkipE2E) {
        Run 'Build' { & npm.cmd run build }
        Run 'Install Playwright Chromium' { & npx.cmd playwright install chromium }
        Run 'End-to-end tests (Playwright)' { & npx.cmd playwright test }
    }
} finally { Pop-Location }
Write-Host 'All test suites passed.' -ForegroundColor Green
