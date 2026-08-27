# Download Qwen2.5-7B-Instruct Q4_K_M GGUF for llama.cpp (~4.7 GB).
# Usage: powershell -File scripts/download-llamacpp-model.ps1

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$ModelsDir = Join-Path $RepoRoot "models"
$OutFile = Join-Path $ModelsDir "Qwen2.5-7B-Instruct-Q4_K_M.gguf"
$Url = "https://huggingface.co/bartowski/Qwen2.5-7B-Instruct-GGUF/resolve/main/Qwen2.5-7B-Instruct-Q4_K_M.gguf"

New-Item -ItemType Directory -Force -Path $ModelsDir | Out-Null

if (Test-Path $OutFile) {
  $sizeGb = [math]::Round((Get-Item $OutFile).Length / 1GB, 2)
  if ($sizeGb -ge 4.0) {
    Write-Host "Model already present: $OutFile (${sizeGb} GB)"
    exit 0
  }
  Write-Host "Incomplete download detected (${sizeGb} GB) — re-downloading…"
  Remove-Item $OutFile -Force
}

Write-Host "Downloading Qwen2.5-7B-Instruct Q4_K_M (~4.7 GB)…"
Write-Host "  -> $OutFile"

$curl = Get-Command curl.exe -ErrorAction SilentlyContinue
if ($curl) {
  & curl.exe -L --retry 5 --retry-delay 2 -C - -o $OutFile $Url
  if ($LASTEXITCODE -ne 0) {
    Write-Error "curl download failed with exit code $LASTEXITCODE"
  }
} else {
  Invoke-WebRequest -Uri $Url -OutFile $OutFile
}

$sizeGb = [math]::Round((Get-Item $OutFile).Length / 1GB, 2)
Write-Host "Done: $OutFile (${sizeGb} GB)"
