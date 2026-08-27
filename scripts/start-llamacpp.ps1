# Start llama-server for RazorFlow (Qwen2.5-7B-Instruct Q4_K_M).
# Usage: powershell -File scripts/start-llamacpp.ps1

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$ModelsDir = Join-Path $RepoRoot "models"
$DefaultModel = Join-Path $ModelsDir "Qwen2.5-7B-Instruct-Q4_K_M.gguf"
$LegacyModel = Join-Path $ModelsDir "qwen2.5-7b-instruct-q4_k_m.gguf"
$ModelPath = if ($env:LLAMACPP_MODEL_PATH) { $env:LLAMACPP_MODEL_PATH } else { $null }
$Port = if ($env:LLAMACPP_PORT) { $env:LLAMACPP_PORT } else { "8080" }
$Ctx = if ($env:LLAMACPP_CTX) { $env:LLAMACPP_CTX } else { "8192" }
$GpuLayers = if ($env:LLAMACPP_N_GPU_LAYERS) { $env:LLAMACPP_N_GPU_LAYERS } else { "99" }
$HfRepo = if ($env:LLAMACPP_HF_REPO) { $env:LLAMACPP_HF_REPO } else { "bartowski/Qwen2.5-7B-Instruct-GGUF:Q4_K_M" }

function Find-LlamaServer {
  $cmd = Get-Command llama-server -ErrorAction SilentlyContinue
  if ($cmd) { return $cmd.Source }

  $wingetLinks = Join-Path $env:LOCALAPPDATA "Microsoft\WinGet\Links\llama-server.exe"
  if (Test-Path $wingetLinks) { return $wingetLinks }

  $packages = Join-Path $env:LOCALAPPDATA "Microsoft\WinGet\Packages"
  if (Test-Path $packages) {
    $found = Get-ChildItem -Path $packages -Filter "llama-server.exe" -Recurse -ErrorAction SilentlyContinue |
      Select-Object -First 1
    if ($found) { return $found.FullName }
  }
  return $null
}

$LlamaServer = Find-LlamaServer
if (-not $LlamaServer) {
  Write-Error "llama-server not found. Install with: winget install ggml.llamacpp"
}

if (-not $ModelPath) {
  if (Test-Path $DefaultModel) { $ModelPath = $DefaultModel }
  elseif (Test-Path $LegacyModel) { $ModelPath = $LegacyModel }
}

Write-Host "Starting llama-server"
Write-Host "  binary : $LlamaServer"
Write-Host "  listen : http://127.0.0.1:$Port  (OpenAI base: /v1)"
Write-Host "  ctx    : $Ctx  n-gpu-layers: $GpuLayers"

if ($ModelPath -and (Test-Path $ModelPath)) {
  Write-Host "  model  : $ModelPath"
  & $LlamaServer `
    -m $ModelPath `
    --port $Port `
    --host 127.0.0.1 `
    -c $Ctx `
    -ngl $GpuLayers `
    --jinja `
    -fa on
} else {
  Write-Host "  model  : Hugging Face $HfRepo (auto-download on first run)"
  & $LlamaServer `
    -hf $HfRepo `
    --port $Port `
    --host 127.0.0.1 `
    -c $Ctx `
    -ngl $GpuLayers `
    --jinja `
    -fa on
}
