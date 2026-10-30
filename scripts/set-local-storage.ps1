# Dot-source before installing dependencies or starting a native model runtime:
# . ./scripts/set-local-storage.ps1
# Changes apply to this PowerShell session and its child processes only.
$ErrorActionPreference = 'Stop'
$storageRepoRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
if ($storageRepoRoot.StartsWith('C:\', [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Keep this checkout on the data drive before configuring model storage.'
}
$storageCacheRoot = Join-Path $storageRepoRoot 'artifacts/model-cache'
$storageOllamaRoot = Join-Path $storageRepoRoot 'artifacts/ollama-home'
$storageVariables = @{
    HF_HOME = Join-Path $storageCacheRoot 'huggingface'
    HF_HUB_CACHE = Join-Path $storageCacheRoot 'huggingface/hub'
    TORCH_HOME = Join-Path $storageCacheRoot 'torch'
    PIP_CACHE_DIR = Join-Path $storageCacheRoot 'pip'
    UV_CACHE_DIR = Join-Path $storageCacheRoot 'uv'
    XDG_CACHE_HOME = $storageCacheRoot
    OLLAMA_MODELS = Join-Path $storageOllamaRoot 'models'
    TEMP = Join-Path $storageCacheRoot 'tmp'
    TMP = Join-Path $storageCacheRoot 'tmp'
    AI_MODEL_CACHE_DIR = $storageCacheRoot.Replace('\', '/')
    AI_OLLAMA_HOME = $storageOllamaRoot.Replace('\', '/')
}
foreach ($storageName in $storageVariables.Keys) {
    $storagePath = [IO.Path]::GetFullPath($storageVariables[$storageName])
    if (-not $storagePath.StartsWith($storageRepoRoot + [IO.Path]::DirectorySeparatorChar,
            [StringComparison]::OrdinalIgnoreCase)) {
        throw 'Cache path must remain inside this checkout.'
    }
    $null = New-Item -ItemType Directory -Path $storagePath -Force
    [Environment]::SetEnvironmentVariable($storageName, $storagePath, 'Process')
}
Write-Output "Model and package caches: $storageCacheRoot"
Write-Output "Ollama models: $storageOllamaRoot/models"
Write-Output 'No packages or models were downloaded. Docker image/build storage is configured separately in Docker Desktop.'
