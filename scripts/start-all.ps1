# RazorFlow - Start All Services
# Usage: powershell -ExecutionPolicy Bypass -File scripts/start-all.ps1

$ErrorActionPreference = "Continue"
$RepoRoot = Split-Path -Parent $PSScriptRoot

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "       [RazorFlow] Starting Stack       " -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

# 1. Environment check
Write-Host "`n[1/4] Checking environment configuration..." -ForegroundColor Yellow
if (Test-Path (Join-Path $RepoRoot "scripts\check_env.py")) {
    python (Join-Path $RepoRoot "scripts\check_env.py")
}

# 2. Build SDK & Extension
Write-Host "`n[2/4] Building SDK packages & Chrome Extension..." -ForegroundColor Yellow
Push-Location $RepoRoot
npm run build:sdk
if ($LASTEXITCODE -ne 0) {
    Write-Host "[WARNING] SDK build failed, continuing..." -ForegroundColor DarkYellow
}
Push-Location (Join-Path $RepoRoot "extension")
npm run build
if ($LASTEXITCODE -ne 0) {
    Write-Host "[WARNING] Extension build failed, continuing..." -ForegroundColor DarkYellow
}
Pop-Location
Pop-Location

# 3. Start Agent Backend (Port 8765)
Write-Host "`n[3/4] Checking Agent Backend (Port 8765)..." -ForegroundColor Yellow
$backendRunning = $false
try {
    $res = Invoke-RestMethod -Uri "http://127.0.0.1:8765/health" -TimeoutSec 2 -ErrorAction Stop
    if ($res.status -eq "ok") {
        $backendRunning = $true
        Write-Host " -> Agent Backend is already running on http://127.0.0.1:8765" -ForegroundColor Green
    }
} catch {
    $backendRunning = $false
}

if (-not $backendRunning) {
    Write-Host " -> Starting Agent Backend in background..." -ForegroundColor Cyan
    Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$RepoRoot'; python agent-backend/main.py"
    Start-Sleep -Seconds 3
}

# 4. Start Fake Store (Port 3001)
Write-Host "`n[4/4] Checking Fake Store (Port 3001)..." -ForegroundColor Yellow
$storeRunning = $false
try {
    $res = Invoke-WebRequest -Uri "http://127.0.0.1:3001" -UseBasicParsing -TimeoutSec 2 -ErrorAction Stop
    if ($res.StatusCode -eq 200) {
        $storeRunning = $true
        Write-Host " -> Fake Store is already running on http://127.0.0.1:3001" -ForegroundColor Green
    }
} catch {
    $storeRunning = $false
}

if (-not $storeRunning) {
    Write-Host " -> Starting Fake Store in background..." -ForegroundColor Cyan
    Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$RepoRoot\fake-store'; npm run dev"
    Start-Sleep -Seconds 3
}

# 5. Final Status Summary
Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "       [RazorFlow] Stack Ready!         " -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  * Fake Store:        http://127.0.0.1:3001" -ForegroundColor Green
Write-Host "  * Agent Backend:     http://127.0.0.1:8765" -ForegroundColor Green
Write-Host "  * Backend Health:    http://127.0.0.1:8765/health" -ForegroundColor Green
Write-Host "  * WebSocket Bridge:  ws://127.0.0.1:8765/ws" -ForegroundColor Green
Write-Host "  * Extension Dist:    $RepoRoot\extension\dist" -ForegroundColor Green
Write-Host ""
Write-Host "To load the Chrome Extension:" -ForegroundColor Yellow
Write-Host "  1. Open Chrome and go to chrome://extensions"
Write-Host "  2. Enable 'Developer mode' (top right toggle)"
Write-Host "  3. Click 'Load unpacked' and select:"
Write-Host "     $RepoRoot\extension\dist"
Write-Host "  4. Open http://127.0.0.1:3001 and start testing!"
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

