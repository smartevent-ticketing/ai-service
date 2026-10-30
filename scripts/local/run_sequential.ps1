param(
    [ValidateSet('check', 'prepare', 'smoke', 'serve')]
    [string]$Mode = 'serve',
    [int]$Port = 8001,
    [string]$ConfigDir,
    [string]$HelpOutput,
    [string]$BaseModelPath,
    [string]$RagBaseModelPath
)
$ErrorActionPreference = 'Stop'
$repoRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../..'))
$pythonPath = Join-Path $repoRoot '.venv/Scripts/python.exe'
$launcherArgs = @('--mode', $Mode, '--port', $Port)
if ($ConfigDir) { $launcherArgs += @('--config-dir', $ConfigDir) }
if ($HelpOutput) { $launcherArgs += @('--help-output', $HelpOutput) }
if ($BaseModelPath) { $launcherArgs += @('--base-model-path', $BaseModelPath) }
if ($RagBaseModelPath) { $launcherArgs += @('--rag-base-model-path', $RagBaseModelPath) }
& $pythonPath -B -u (Join-Path $PSScriptRoot 'run_sequential.py') @launcherArgs
exit $LASTEXITCODE
