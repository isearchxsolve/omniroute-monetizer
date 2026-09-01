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
$PythonExe = (Get-Command python -ErrorAction Stop).Source

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

function Get-NssmSetting([string]$Name) {
    # NSSM is the registered service owner.  Read the exact string it will use,
    # so a rollback restores the real launch definition instead of hoping a
    # registry import is immediately reflected in the service manager cache.
    $value = @(& $NssmExe get $ServiceName $Name)
    if ($LASTEXITCODE -ne 0 -or -not $value) {
        throw "Could not read NSSM setting $Name for $ServiceName."
    }
    return (($value | Select-Object -Last 1).ToString()).Trim()
}

function Set-And-VerifyNssmSetting([string]$Name, [string]$Value) {
    & $NssmExe set $ServiceName $Name $Value | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Could not set NSSM $Name for $ServiceName." }
    $actual = Get-NssmSetting $Name
    if ($actual -ne $Value) {
        throw "NSSM $Name verification failed after update."
    }
}

function Get-AuthenticatedModelProbe([int]$TimeoutSeconds = 60) {
    # /v1/models is intentionally management-auth protected on the production
    # state.  A bare HTTP request therefore proves only that auth is enabled
    # (401), not that the candidate catalog failed.  This isolated short-lived
    # Python client obtains the existing local DPAPI-protected management
    # password, establishes an auth_token cookie, then returns redacted
    # structural facts only.  It never logs the password or cookie.
    $probe = @'
import json, sys, time
import requests
from pathlib import Path
root = Path(r"D:\omniroute-monetizer")
sys.path.insert(0, str(root / "scripts" / "automation"))
from password_vault import retrieve_password
base = "http://127.0.0.1:20128"
s = requests.Session()
s.trust_env = False
started = time.perf_counter()
try:
    login = s.post(base + "/api/auth/login", json={"password": retrieve_password().strip()}, timeout=120)
    if login.status_code != 200:
        raise RuntimeError("management login HTTP %s" % login.status_code)
    response = s.get(base + "/v1/models", timeout=int(sys.argv[1]))
    payload = response.json() if response.ok else {}
    rows = payload.get("data", []) if isinstance(payload, dict) else []
    print(json.dumps({"ok": response.status_code == 200 and isinstance(rows, list), "status": response.status_code, "count": len(rows), "elapsedMs": round((time.perf_counter() - started) * 1000, 1)}))
except Exception as exc:
    print(json.dumps({"ok": False, "status": None, "count": 0, "elapsedMs": round((time.perf_counter() - started) * 1000, 1), "error": "%s: %s" % (type(exc).__name__, str(exc)[:220])}))
'@
    $raw = @(& $PythonExe -c $probe $TimeoutSeconds)
    if ($LASTEXITCODE -ne 0 -or -not $raw) {
        throw 'Authenticated model probe process failed before producing a result.'
    }
    try { return (($raw | Select-Object -Last 1) | ConvertFrom-Json) }
    catch { throw 'Authenticated model probe returned invalid JSON.' }
}

function Invoke-Robocopy([string]$From, [string]$To, [switch]$Mirror) {
    $args = @($From, $To, '/E', '/COPY:DAT', '/DCOPY:T', '/R:2', '/W:1', '/XJ', '/NFL', '/NDL', '/NP')
    if ($Mirror) { $args = @($From, $To, '/MIR', '/COPY:DAT', '/DCOPY:T', '/R:2', '/W:1', '/XJ', '/NFL', '/NDL', '/NP') }
    & robocopy.exe @args | Out-Null
    if ($LASTEXITCODE -gt 7) { throw "robocopy failed with exit code $LASTEXITCODE" }
}

function Write-CriticalStateManifest([string]$Root, [string]$OutputFile) {
    # The complete stopped-state tree is copied.  Hash the four state-bearing
    # files needed to restore encrypted provider state, not every historical
    # call/Qoder log that happens to live under DATA_DIR.  This keeps the
    # recovery gate bounded and avoids one archival file preventing a rollback.
    $critical = @('.env', 'storage.sqlite', 'storage.sqlite-wal', 'storage.sqlite-shm')
    $rows = foreach ($relative in $critical) {
        $path = Join-Path $Root $relative
        if (-not (Test-Path -LiteralPath $path)) { throw "Critical state file missing from stopped snapshot: $relative" }
        $item = Get-Item -LiteralPath $path -Force
        [pscustomobject]@{ path = $relative; bytes = $item.Length; sha256 = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash }
    }
    [pscustomobject]@{
        criticalFiles = $rows
        totalFiles = (Get-ChildItem -LiteralPath $Root -File -Force -Recurse | Measure-Object).Count
    } | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $OutputFile -Encoding UTF8
}

function Restore-Production([string]$BackupDir, [string]$ServiceRegBackup, [string]$OriginalAppDirectory, [string]$OriginalAppParameters) {
    Write-Warning 'Candidate validation failed. Restoring service configuration and byte-for-byte state snapshot.'
    Stop-Service -Name $ServiceName -ErrorAction SilentlyContinue
    Wait-ServiceStopped
    # Both paths are fixed constants and the backup is created in this run;
    # /MIR is intentionally limited to the exact live OmniRoute data root.
    Invoke-Robocopy -From (Join-Path $BackupDir 'data') -To $LiveDataDir -Mirror
    & reg.exe import $ServiceRegBackup | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Rollback could not restore the saved OmniRoute service registry configuration.' }
    # Registry import preserves every service setting, including the encrypted
    # environment lineage.  Explicitly reapply and verify the two values this
    # cutover changes because SCM/NSSM can retain a stale in-memory view after
    # an import.  This closes the first-run rollback ambiguity.
    Set-And-VerifyNssmSetting -Name 'AppDirectory' -Value $OriginalAppDirectory
    Set-And-VerifyNssmSetting -Name 'AppParameters' -Value $OriginalAppParameters
    Start-Service -Name $ServiceName
}

Assert-Path $LiveDataDir 'Production DATA_DIR'
Assert-Path $CandidateEntry 'Staged OmniRoute 3.8.50 entry point'
Assert-Path $CandidateAppDir 'Staged OmniRoute 3.8.50 application directory'
Assert-Path $NodeExe 'Pinned Node runtime'
Assert-Path $NssmExe 'NSSM service manager'
$null = $PythonExe

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
$transcriptFile = Join-Path $runDir 'cutover-transcript.txt'
$serviceRegBackup = Join-Path $backupDir 'OmniRoute-service-before.reg'
New-Item -ItemType Directory -Path (Join-Path $backupDir 'data') -Force | Out-Null

$report = [ordered]@{
    startedAt = (Get-Date).ToUniversalTime().ToString('o')
    service = $ServiceName
    fromVersion = '3.8.49'
    toVersion = '3.8.50'
    stateBackup = $backupDir
    serviceRegistryBackup = $serviceRegBackup
    transcript = $transcriptFile
    probes = @()
    result = 'RUNNING'
}
$originalAppDirectory = $null
$originalAppParameters = $null

try {
    Start-Transcript -LiteralPath $transcriptFile -Append | Out-Null
    # Preserve the exact NSSM configuration before changing one parameter. The
    # export also preserves the encrypted-key environment lineage, but it is
    # retained only inside the gitignored recovery directory.
    & reg.exe export 'HKLM\SYSTEM\CurrentControlSet\Services\OmniRoute' $serviceRegBackup /y | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Could not export the current OmniRoute service registry configuration.' }
    $originalAppDirectory = Get-NssmSetting 'AppDirectory'
    $originalAppParameters = Get-NssmSetting 'AppParameters'

    Stop-Service -Name $ServiceName
    Wait-ServiceStopped
    Invoke-Robocopy -From $LiveDataDir -To (Join-Path $backupDir 'data')
    Write-CriticalStateManifest -Root $LiveDataDir -OutputFile (Join-Path $backupDir 'live-state-sha256.json')
    Write-CriticalStateManifest -Root (Join-Path $backupDir 'data') -OutputFile (Join-Path $backupDir 'backup-state-sha256.json')

    # Change only executable arguments and application directory. Existing
    # service environment (DATA_DIR and encryption lineage) is deliberately
    # preserved verbatim by not rewriting AppEnvironmentExtra.
    Set-And-VerifyNssmSetting -Name 'AppDirectory' -Value $CandidateAppDir
    $params = "--max-old-space-size=4096 `"$CandidateEntry`" serve --port 20128 --no-open --no-tray --no-recovery --log"
    Set-And-VerifyNssmSetting -Name 'AppParameters' -Value $params

    Start-Service -Name $ServiceName
    $initialHealth = Wait-CandidateHealthy
    $report.initialHealth = [ordered]@{ status = $initialHealth.status; elapsedMs = $initialHealth.elapsedMs }

    for ($round = 1; $round -le $ProbeRounds; $round++) {
        $health = Get-HttpJson '/api/monitoring/health' 15
        $models = Get-AuthenticatedModelProbe 60
        $modelCount = $models.count
        $modelError = if ($models.PSObject.Properties.Name -contains 'error') { $models.error } else { $null }
        $row = [ordered]@{
            round = $round
            at = (Get-Date).ToUniversalTime().ToString('o')
            health = [ordered]@{ ok = $health.ok; status = $health.status; elapsedMs = $health.elapsedMs }
            models = [ordered]@{ ok = $models.ok; status = $models.status; elapsedMs = $models.elapsedMs; count = $modelCount; error = $modelError }
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
    Stop-Transcript | Out-Null
    Write-Output "SUCCESS: OmniRoute 3.8.50 promoted and validated. Redacted report: $reportFile"
} catch {
    $failure = $_.Exception.Message
    $report.result = 'CANDIDATE_FAILED_ROLLBACK_REQUESTED'
    $report.failure = $failure
    $report.failedAt = (Get-Date).ToUniversalTime().ToString('o')
    try {
        if (-not $originalAppDirectory -or -not $originalAppParameters) {
            throw 'Rollback launch settings were not captured before the failure.'
        }
        Restore-Production -BackupDir $backupDir -ServiceRegBackup $serviceRegBackup -OriginalAppDirectory $originalAppDirectory -OriginalAppParameters $originalAppParameters
        $report.result = 'CANDIDATE_FAILED_ROLLED_BACK'
    } catch {
        $report.result = 'CANDIDATE_FAILED_ROLLBACK_FAILED'
        $report.rollbackFailure = $_.Exception.Message
    }
    $report | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $reportFile -Encoding UTF8
    try { Stop-Transcript | Out-Null } catch {}
    throw "CUTOVER FAILED: $failure. See redacted report: $reportFile"
}
