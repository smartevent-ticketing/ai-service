param(
    [ValidateSet('check', 'smoke', 'serve', 'verify')]
    [string]$Mode = 'serve',
    [int]$Port = 8001,
    [string]$SearchConfigDir,
    [string]$BackendBaseUrl = 'http://127.0.0.1:8080'
)
$ErrorActionPreference = 'Stop'
$repoRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$pythonPath = Join-Path $repoRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw "Python environment missing: $pythonPath"
}
$launcherArgs = @('--mode', $Mode, '--port', $Port, '--backend', $BackendBaseUrl)
if ($SearchConfigDir) { $launcherArgs += @('--search-config-dir', $SearchConfigDir) }
& $pythonPath -B -u (Join-Path $PSScriptRoot 'run_peft.py') @launcherArgs
exit $LASTEXITCODE
