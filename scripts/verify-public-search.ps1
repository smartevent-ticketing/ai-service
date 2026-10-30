param(
    [string]$BackendRepo = (Join-Path $PSScriptRoot '../../smartevent-backend'),
    [string]$AiImage = 'smartevent-ai-service:local-public-search',
    [string]$BackendImage = 'smartevent-backend:local',
    [string]$OutputDirectory = (Join-Path $PSScriptRoot '../artifacts/local-public-search'),
    [string]$VerifierScript = 'scripts/public_search_deployment.py',
    [string]$AdditionalFixture = ''
)
$ErrorActionPreference = 'Stop'
$aiRepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$backendRepoRoot = (Resolve-Path $BackendRepo).Path
$outputRoot = [IO.Path]::GetFullPath($OutputDirectory)
if (Test-Path -LiteralPath $outputRoot) { throw 'Output directory must be new; preserve previous evidence.' }
$jarPath = Join-Path $backendRepoRoot 'build/libs/smart-event-backend-0.0.1-SNAPSHOT.jar'
if (-not (Test-Path -LiteralPath $jarPath)) { throw 'Build the backend bootJar first.' }
New-Item -ItemType Directory -Path $outputRoot | Out-Null
$fixtureSuffix = [Guid]::NewGuid().ToString('N').Substring(0, 10)
$fixtureNetwork = "ai-search-$fixtureSuffix"
$fixtureDb = "ai-search-db-$fixtureSuffix"
$fixtureBackend = "ai-search-backend-$fixtureSuffix"
function Invoke-FixtureDocker {
    $dockerOutput = & docker @args
    if ($LASTEXITCODE -ne 0) { throw "Docker failed: $($args[0])" }
    return $dockerOutput
}
function Get-FixtureSnapshot {
    $fixtureDump = Invoke-FixtureDocker exec $fixtureDb pg_dump -U fixture -d ai_search_test --data-only --inserts --column-inserts --no-owner --no-privileges
    $fixtureCanonical = ($fixtureDump | Where-Object { $_ -match '^(INSERT INTO|SELECT pg_catalog.setval)' } | Sort-Object) -join "`n"
    return [Convert]::ToHexString([Security.Cryptography.SHA256]::HashData([Text.Encoding]::UTF8.GetBytes($fixtureCanonical))).ToLowerInvariant()
}
try {
    $null = Invoke-FixtureDocker network create $fixtureNetwork
    $null = Invoke-FixtureDocker run -d --name $fixtureDb --network $fixtureNetwork --tmpfs /var/lib/postgresql/data:rw -e POSTGRES_DB=ai_search_test -e POSTGRES_USER=fixture -e POSTGRES_HOST_AUTH_METHOD=trust postgres:16-alpine
    $null = Invoke-FixtureDocker run -d --name $fixtureBackend --network $fixtureNetwork --mount "type=bind,source=$jarPath,target=/app/app.jar,readonly" -e "SPRING_DATASOURCE_URL=jdbc:postgresql://${fixtureDb}:5432/ai_search_test" -e SPRING_DATASOURCE_USERNAME=fixture -e SPRING_DATASOURCE_PASSWORD=fixture -e JWT_SECRET=VGhpcy1pcy1hLWxvY2FsLXRlc3Qta2V5LW9ubHktMzItYnl0ZXM= -e SPRING_RABBITMQ_USERNAME=fixture -e SPRING_RABBITMQ_PASSWORD=fixture -e SPRING_RABBITMQ_LISTENER_SIMPLE_AUTO_STARTUP=false -e APP_MINIO_ACCESS_KEY=fixture -e APP_MINIO_SECRET_KEY=fixture-secret -e APP_MAIL_ENABLED=false $BackendImage
    $readyCode = @'
import sys, time, urllib.request
for attempt in range(60):
    try:
        with urllib.request.urlopen(sys.argv[1], timeout=2) as response:
            if response.status == 200: break
    except Exception:
        time.sleep(1)
else:
    raise SystemExit('Disposable backend not ready')
'@
    $null = Invoke-FixtureDocker run --rm --network $fixtureNetwork $AiImage python -c $readyCode "http://${fixtureBackend}:8080/api/v1/events?size=1"
    $null = Invoke-FixtureDocker cp (Join-Path $aiRepoRoot 'tests/fixtures/public_search.sql') "${fixtureDb}:/tmp/fixture.sql"
    $null = Invoke-FixtureDocker exec $fixtureDb psql -X -v ON_ERROR_STOP=1 -U fixture -d ai_search_test -f /tmp/fixture.sql
    if ($AdditionalFixture) {
        $null = Invoke-FixtureDocker cp (Join-Path $aiRepoRoot $AdditionalFixture) "${fixtureDb}:/tmp/price-fixture.sql"
        $null = Invoke-FixtureDocker exec $fixtureDb psql -X -v ON_ERROR_STOP=1 -U fixture -d ai_search_test -f /tmp/price-fixture.sql
    }
    $before = Get-FixtureSnapshot
    $reportPath = Join-Path $outputRoot 'live-evidence.json'
    $null = Invoke-FixtureDocker run --rm --network $fixtureNetwork --mount "type=bind,source=$aiRepoRoot,target=/workspace,readonly" --mount "type=bind,source=$outputRoot,target=/evidence" --workdir /workspace -e PYTHONPATH=/workspace/src $AiImage python $VerifierScript verify --backend "http://${fixtureBackend}:8080" --report /evidence/live-evidence.json
    $after = Get-FixtureSnapshot
    if ($before -cne $after) { throw 'Fixture database changed during read-only tests; deployment stays disabled.' }
    $report = Get-Content -LiteralPath $reportPath -Raw | ConvertFrom-Json
    $report.database_snapshot_before = $before
    $report.database_snapshot_after = $after
    $report.note = 'Independent full-row fixture database digests match before/after live tests.'
    $report | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath $reportPath -Encoding utf8
    $null = Invoke-FixtureDocker run --rm --mount "type=bind,source=$aiRepoRoot,target=/workspace,readonly" --mount "type=bind,source=$outputRoot,target=/evidence" --workdir /workspace -e PYTHONPATH=/workspace/src $AiImage python $VerifierScript prepare --report /evidence/live-evidence.json --output /evidence/configs
    Write-Output "Verified local public-search config: $(Join-Path $outputRoot 'configs')"
} finally {
    & docker rm -f $fixtureBackend $fixtureDb 2>$null | Out-Null
    & docker network rm $fixtureNetwork 2>$null | Out-Null
}
