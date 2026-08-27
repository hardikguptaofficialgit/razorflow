# After the GGUF finishes downloading, start llama-server automatically.
# Usage: powershell -File scripts/wait-and-start-llamacpp.ps1

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$Model = Join-Path $RepoRoot "models\Qwen2.5-7B-Instruct-Q4_K_M.gguf"
$MinBytes = [int64](4300MB)  # bartowski Q4_K_M is ~4466 MB; require near-complete file

Write-Host "Waiting for model at $Model (>= 4 GB)..."
while ($true) {
  if (Test-Path $Model) {
    $len = (Get-Item $Model).Length
    $mb = [math]::Round($len / 1MB, 1)
    Write-Host ("  have {0} MB" -f $mb)
    if ($len -ge $MinBytes) { break }
  } else {
    Write-Host "  model file not found yet"
  }
  Start-Sleep -Seconds 30
}

Write-Host "Model ready - starting llama-server"
& (Join-Path $PSScriptRoot "start-llamacpp.ps1")
