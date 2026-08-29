# Publish all RazorFlow SDK packages using NPM_TOKEN (granular access token).
# Usage: $env:NPM_TOKEN = "npm_..."; .\packages\publish-sdk.ps1

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

if (-not $env:NPM_TOKEN) {
    Write-Host "Set NPM_TOKEN first:" -ForegroundColor Yellow
    Write-Host '  $env:NPM_TOKEN = "npm_your_granular_access_token"' -ForegroundColor Cyan
    Write-Host "Create one at: https://www.npmjs.com/settings/hardik21232323/tokens" -ForegroundColor Gray
    exit 1
}

# Write project .npmrc (gitignored) — npm config set was not applying the token correctly
$npmrcPath = Join-Path $root ".npmrc"
@(
    "registry=https://registry.npmjs.org/"
    "//registry.npmjs.org/:_authToken=$($env:NPM_TOKEN)"
) | Set-Content -Path $npmrcPath -Encoding utf8

Write-Host "Verifying npm auth..." -ForegroundColor Green
npm whoami
if ($LASTEXITCODE -ne 0) {
    Write-Host "Token invalid or expired. Create a new granular token." -ForegroundColor Red
    exit 1
}

Write-Host "Building SDK..." -ForegroundColor Green
npm run build:sdk
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
npm run test:sdk
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$packages = @(
    "@hardik21232323/razorflow-protocol",
    "@hardik21232323/razorflow-browser",
    "@hardik21232323/razorflow-client"
)

foreach ($pkg in $packages) {
    Write-Host "Publishing $pkg ..." -ForegroundColor Green
    npm publish -w $pkg --access public
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Failed: $pkg" -ForegroundColor Red
        exit $LASTEXITCODE
    }
}

Write-Host ""
Write-Host "Published successfully:" -ForegroundColor Green
foreach ($pkg in $packages) {
    Write-Host "  https://www.npmjs.com/package/$pkg"
}
