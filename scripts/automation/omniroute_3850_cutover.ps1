[CmdletBinding()]
param(
    [switch]$Apply,
    [int]$StartupTimeoutSeconds = 240,
    [int]$ProbeIntervalSeconds = 70,
    [int]$ProbeRounds = 3
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

# This script deliberately uses the existing NSSM service as the one and only
# owner of direct OmniRoute.  It never kills node.exe by PID: stopping the
# service gives its CLI/child process its normal shutdown path, then makes the
# SQLite database/WAL safe to copy as one stopped-state snapshot.
$ServiceName = 'OmniRoute'
$LiveDataDir = 'C:\Users\Admin\.omniroute'
$RepoRoot = 'D:\omniroute-monetizer'
$StagedRoot = Join-Path $RepoRoot 'state\omniroute-3.8.50-sandbox'
$CandidateEntry = Join-Path $StagedRoot 'node_modules\omniroute\bin\omniroute.mjs'
$CandidateAppDir = Join-Path $StagedRoot 'node_modules\omniroute'
$NodeExe = 'C:\Users\Admin\AppData\Local\hermes\node\node.exe'
$NssmExe = 'C:\Users\Admin\AppData\Local\Microsoft\WinGet\Packages\NSSM.NSSM_Microsoft.Winget.Source_8wekyb3d8bbwe\nssm-2.24-101-g897c7ad\win64\nssm.exe'
$CutoverRoot = Join-Path $RepoRoot 'state\omniroute-cutovers'

function Assert-Administrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw 'This cutover must run from an elevated Administrator PowerShell because it changes only the Windows service configuration.'
    }
}

function Assert-Path([string]$Path, [string]$Description) {
    if (-not (Test-Path -LiteralPath $Path)) {
        throw "$Description is missing: $Path"
    }
}

function Get-HttpJson([string]$Path, [int]$TimeoutSeconds = 15) {
    # Bypass the machine's loopback proxy.  The project contract requires
    # 127.0.0.1 rather than localhost for this exact reason.
    $url = "http://127.0.0.1:20128$Path"
    $watch = [Diagnostics.Stopwatch]::StartNew()
    $request = [System.Net.HttpWebRequest]::Create($url)
    $request.Proxy = $null
    $request.Timeout = $TimeoutSeconds * 1000
    $request.ReadWriteTimeout = $TimeoutSeconds * 1000
    try {
        $response = $request.GetResponse()
        $reader = New-Object IO.StreamReader($response.GetResponseStream())
        $body = $reader.ReadToEnd()
        $reader.Dispose()
        $response.Close()
        $watch.Stop()
        return [pscustomobject]@{
            ok = $true; status = [int]$response.StatusCode
            elapsedMs = [math]::Round($watch.Elapsed.TotalMilliseconds, 1)
            bytes = [Text.Encoding]::UTF8.GetByteCount($body); body = $body
        }
    } catch {
        $watch.Stop()
        return [pscustomobject]@{
            ok = $false; status = $null
            elapsedMs = [math]::Round($watch.Elapsed.TotalMilliseconds, 1)
            bytes = 0; body = $null; error = $_.Exception.Message
        }
    }
}

function Wait-ServiceStopped {
    $deadline = (Get-Date).AddSeconds(90)
    do {
        $svc = Get-Service -Name $ServiceName
        $listener = Get-NetTCPConnection -LocalPort 20128 -State Listen -ErrorAction SilentlyContinue
        if ($svc.Status -eq 'Stopped' -and -not $listener) { return }
        Start-Sleep -Seconds 2
    } while ((Get-Date) -lt $deadline)
    throw 'OmniRoute did not stop cleanly within 90 seconds; refusing to copy live SQLite state.'
}

function Wait-CandidateHealthy {
    $deadline = (Get-Date).AddSeconds($StartupTimeoutSeconds)
    do {
        $result = Get-HttpJson '/api/monitoring/health' 10
        if ($result.ok -and $result.status -eq 200) { return $result }
        Start-Sleep -Seconds 3
    } while ((Get-Date) -lt $deadline)
    throw "Candidate did not return HTTP 200 health inside $StartupTimeoutSeconds seconds."
}

function Invoke-Robocopy([string]$From, [string]$To, [switch]$Mirror) {
    $args = @($From, $To, '/E', '/COPY:DAT', '/DCOPY:T', '/R:2', '/W:1', '/XJ', '/NFL', '/NDL', '/NP')
    if ($Mirror) { $args = @($From, $To, '/MIR', '/COPY:DAT', '/DCOPY:T', '/R:2', '/W:1', '/XJ', '/NFL', '/NDL', '/NP') }
    & robocopy.exe @args | Out-Null
    if ($LASTEXITCODE -gt 7) { throw "robocopy failed with exit code $LASTEXITCODE" }
}

function Write-HashManifest([string]$Root, [string]$OutputFile) {
    # Hashes prove copied bytes without writing any secret material into logs.
    Get-ChildItem -LiteralPath $Root -File -Force -Recurse |
        Sort-Object FullName |
        ForEach-Object {
            $relative = $_.FullName.Substring($Root.Length).TrimStart('\\')
            [pscustomobject]@{ path = $relative; bytes = $_.Length; sha256 = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash }
        } | ConvertTo-Json -Depth 3 | Set-Content -LiteralPath $OutputFile -Encoding UTF8
}

function Restore-Production([string]$BackupDir, [string]$ServiceRegBackup) {
    Write-Warning 'Candidate validation failed. Restoring service configuration and byte-for-byte state snapshot.'
    Stop-Service -Name $ServiceName -ErrorAction SilentlyContinue
    Wait-ServiceStopped
    # Both paths are fixed constants and the backup is created in this run;
    # /MIR is intentionally limited to the exact live OmniRoute data root.
    Invoke-Robocopy -From (Join-Path $BackupDir 'data') -To $LiveDataDir -Mirror
    & reg.exe import $ServiceRegBackup | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Rollback could not restore the saved OmniRoute service registry configuration.' }
    Start-Service -Name $ServiceName
}

Assert-Path $LiveDataDir 'Production DATA_DIR'
Assert-Path $CandidateEntry 'Staged OmniRoute 3.8.50 entry point'
Assert-Path $CandidateAppDir 'Staged OmniRoute 3.8.50 application directory'
Assert-Path $NodeExe 'Pinned Node runtime'
Assert-Path $NssmExe 'NSSM service manager'

$package = Get-Content -LiteralPath (Join-Path $CandidateAppDir 'package.json') -Raw | ConvertFrom-Json
if ($package.version -ne '3.8.50') { throw "Expected staged OmniRoute 3.8.50, found $($package.version)." }

$service = Get-CimInstance Win32_Service -Filter "Name='$ServiceName'"
if (-not $service -or $service.State -ne 'Running') { throw 'The expected direct OmniRoute Windows service is not running; refusing cutover from an unknown state.' }

$plan = [pscustomobject]@{
    service = $ServiceName
    currentVersion = '3.8.49 (verified through live health before cutover)'
    candidateVersion = $package.version
    liveDataDir = $LiveDataDir
    candidateEntry = $CandidateEntry
    probeRounds = $ProbeRounds
    probeIntervalSeconds = $ProbeIntervalSeconds
    rollback = 'restore NSSM registry export and exact stopped-state data snapshot, then start original service'
}

if (-not $Apply) {
    $plan | ConvertTo-Json -Depth 4
    Write-Output 'PLAN_ONLY: no service, state, package, credential, or consumer change was made. Re-run elevated with -Apply to execute.'
    exit 0
}

Assert-Administrator
if ($ProbeRounds -lt 3 -or $ProbeIntervalSeconds -lt 61) {
    throw 'Refusing insufficient validation: use at least 3 probe rounds and a probe interval greater than the known 60-second catalog TTL.'
}

New-Item -ItemType Directory -Path $CutoverRoot -Force | Out-Null
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$runDir = Join-Path $CutoverRoot "3.8.50-$stamp"
$backupDir = Join-Path $runDir 'backup'
$reportFile = Join-Path $runDir 'cutover-report.json'
$serviceRegBackup = Join-Path $backupDir 'OmniRoute-service-before.reg'
New-Item -ItemType Directory -Path (Join-Path $backupDir 'data') -Force | Out-Null

$report = [ordered]@{
    startedAt = (Get-Date).ToUniversalTime().ToString('o')
    service = $ServiceName
    fromVersion = '3.8.49'
    toVersion = '3.8.50'
    stateBackup = $backupDir
    serviceRegistryBackup = $serviceRegBackup
    probes = @()
    result = 'RUNNING'
}

try {
    # Preserve the exact NSSM configuration before changing one parameter. The
    # export also preserves the encrypted-key environment lineage, but it is
    # retained only inside the gitignored recovery directory.
    & reg.exe export 'HKLM\SYSTEM\CurrentControlSet\Services\OmniRoute' $serviceRegBackup /y | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Could not export the current OmniRoute service registry configuration.' }

    Stop-Service -Name $ServiceName
    Wait-ServiceStopped
    Invoke-Robocopy -From $LiveDataDir -To (Join-Path $backupDir 'data')
    Write-HashManifest -Root $LiveDataDir -OutputFile (Join-Path $backupDir 'live-state-sha256.json')
    Write-HashManifest -Root (Join-Path $backupDir 'data') -OutputFile (Join-Path $backupDir 'backup-state-sha256.json')

    # Change only executable arguments and application directory. Existing
    # service environment (DATA_DIR and encryption lineage) is deliberately
    # preserved verbatim by not rewriting AppEnvironmentExtra.
    & $NssmExe set $ServiceName AppDirectory $CandidateAppDir | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Could not point NSSM AppDirectory to the staged candidate.' }
    $params = "--max-old-space-size=4096 `"$CandidateEntry`" serve --port 20128 --no-open --no-tray --no-recovery --log"
    & $NssmExe set $ServiceName AppParameters $params | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Could not point NSSM AppParameters to the staged candidate.' }

    Start-Service -Name $ServiceName
    $initialHealth = Wait-CandidateHealthy
    $report.initialHealth = [ordered]@{ status = $initialHealth.status; elapsedMs = $initialHealth.elapsedMs }

    for ($round = 1; $round -le $ProbeRounds; $round++) {
        $health = Get-HttpJson '/api/monitoring/health' 15
        $models = Get-HttpJson '/v1/models' 45
        $modelCount = $null
        if ($models.ok) {
            try { $modelCount = @((ConvertFrom-Json $models.body).data).Count } catch { throw 'Candidate returned a non-OpenAI models payload.' }
        }
        $row = [ordered]@{
            round = $round
            at = (Get-Date).ToUniversalTime().ToString('o')
            health = [ordered]@{ ok = $health.ok; status = $health.status; elapsedMs = $health.elapsedMs }
            models = [ordered]@{ ok = $models.ok; status = $models.status; elapsedMs = $models.elapsedMs; bytes = $models.bytes; count = $modelCount }
        }
        $report.probes += $row
        if (-not $health.ok -or $health.status -ne 200 -or -not $models.ok -or $models.status -ne 200 -or $modelCount -lt 9000) {
            throw "Candidate failed validation round $round."
        }
        if ($round -lt $ProbeRounds) { Start-Sleep -Seconds $ProbeIntervalSeconds }
    }
    $report.result = 'PROMOTED_AND_VALIDATED'
    $report.finishedAt = (Get-Date).ToUniversalTime().ToString('o')
    $report | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $reportFile -Encoding UTF8
    Write-Output "SUCCESS: OmniRoute 3.8.50 promoted and validated. Redacted report: $reportFile"
} catch {
    $failure = $_.Exception.Message
    $report.result = 'CANDIDATE_FAILED_ROLLBACK_REQUESTED'
    $report.failure = $failure
    $report.failedAt = (Get-Date).ToUniversalTime().ToString('o')
    try {
        Restore-Production -BackupDir $backupDir -ServiceRegBackup $serviceRegBackup
        $report.result = 'CANDIDATE_FAILED_ROLLED_BACK'
    } catch {
        $report.result = 'CANDIDATE_FAILED_ROLLBACK_FAILED'
        $report.rollbackFailure = $_.Exception.Message
    }
    $report | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $reportFile -Encoding UTF8
    throw "CUTOVER FAILED: $failure. See redacted report: $reportFile"
}
