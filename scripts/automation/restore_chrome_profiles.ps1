[CmdletBinding()]
param(
    [ValidateSet('Backup', 'List', 'Finalize', 'RepairRegistry', 'Restore')]
    [string]$Mode = 'Backup',

    [string]$ChromeUserData = (Join-Path $env:LOCALAPPDATA 'Google\Chrome\User Data'),

    [string]$BackupRoot = 'D:\omniroute-backups\chrome-profiles',

    [string]$Snapshot,

    [switch]$ConfirmRestore,

    [switch]$ConfirmRegistryRepair
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Get-ManagedProfiles {
    param([Parameter(Mandatory)][string]$Root)

    if (-not (Test-Path -LiteralPath $Root -PathType Container)) {
        throw "Chrome User Data directory does not exist: $Root"
    }

    $profiles = Get-ChildItem -LiteralPath $Root -Directory | Where-Object {
        $_.Name -eq 'Default' -or $_.Name -match '^Profile \d+$'
    }
    if (-not $profiles) {
        throw "No Chrome profile directories were found under: $Root"
    }
    return @($profiles)
}

function Stop-ChromeForRecovery {
    $processes = @(Get-Process -Name chrome -ErrorAction SilentlyContinue)
    if ($processes.Count -eq 0) {
        return
    }

    Write-Warning "Stopping $($processes.Count) running Chrome process(es) before recovery."
    $processes | Stop-Process -Force
    Start-Sleep -Milliseconds 500
    if (Get-Process -Name chrome -ErrorAction SilentlyContinue) {
        throw 'Chrome is still running. Close it completely, then rerun the command.'
    }
}

function Test-Snapshot {
    param([Parameter(Mandatory)][string]$Path)

    if (-not (Test-Path -LiteralPath $Path -PathType Container)) {
        throw "Snapshot directory does not exist: $Path"
    }
    if (-not (Test-Path -LiteralPath (Join-Path $Path 'Local State') -PathType Leaf)) {
        throw "Snapshot is incomplete: missing Local State at $Path"
    }
    $profiles = Get-ManagedProfiles -Root $Path
    foreach ($profile in $profiles) {
        if (-not (Test-Path -LiteralPath (Join-Path $profile.FullName 'Network\Cookies') -PathType Leaf)) {
            throw "Snapshot is incomplete: $($profile.Name) has no Network\\Cookies database."
        }
    }
    return $profiles
}

function New-Snapshot {
    param(
        [Parameter(Mandatory)][string]$Source,
        [Parameter(Mandatory)][string]$DestinationRoot
    )

    Stop-ChromeForRecovery
    $profiles = Get-ManagedProfiles -Root $Source
    $localState = Join-Path $Source 'Local State'
    if (-not (Test-Path -LiteralPath $localState -PathType Leaf)) {
        throw "Chrome Local State is missing: $localState"
    }

    $stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
    $staging = Join-Path $DestinationRoot "chrome_profile_$stamp.incomplete"
    $destination = Join-Path $DestinationRoot "chrome_profile_$stamp"
    New-Item -ItemType Directory -Path $staging -Force | Out-Null

    try {
        Copy-Item -LiteralPath $localState -Destination (Join-Path $staging 'Local State') -Force
        foreach ($profile in $profiles) {
            Copy-Item -LiteralPath $profile.FullName -Destination (Join-Path $staging $profile.Name) -Recurse -Force
        }
        $copiedProfiles = Test-Snapshot -Path $staging
        $manifest = [ordered]@{
            schema = 1
            createdAt = (Get-Date).ToString('o')
            source = $Source
            profiles = @($copiedProfiles.Name)
            note = 'Browser cookies remain protected by the original Windows user account. Restore under the same Windows account.'
        } | ConvertTo-Json
        # `utf8NoBOM` exists in PowerShell 7+, but the operator's Windows PowerShell 5.1
        # accepts only `UTF8`. JSON readers accept the resulting UTF-8 BOM, so favor broad
        # compatibility for an emergency-recovery tool.
        Set-Content -LiteralPath (Join-Path $staging 'snapshot.json') -Value $manifest -Encoding UTF8
        Move-Item -LiteralPath $staging -Destination $destination
        Write-Output "Backup complete: $destination"
        return $destination
    }
    catch {
        Write-Warning "Backup was not finalized; incomplete copy preserved at: $staging"
        throw
    }
}

function Complete-StagingSnapshot {
    param([Parameter(Mandatory)][string]$Path)

    $stagingPath = (Resolve-Path -LiteralPath $Path).Path
    if ($stagingPath -notmatch '\.incomplete$') {
        throw "Refusing to finalize a non-staging directory: $stagingPath"
    }
    $profiles = Test-Snapshot -Path $stagingPath
    $finalPath = $stagingPath -replace '\.incomplete$', ''
    if (Test-Path -LiteralPath $finalPath) {
        throw "Refusing to overwrite an existing finalized snapshot: $finalPath"
    }
    $manifest = [ordered]@{
        schema = 1
        createdAt = (Get-Date).ToString('o')
        source = 'Finalized from a previously complete staging backup.'
        profiles = @($profiles.Name)
        note = 'Browser cookies remain protected by the original Windows user account. Restore under the same Windows account.'
    } | ConvertTo-Json
    Set-Content -LiteralPath (Join-Path $stagingPath 'snapshot.json') -Value $manifest -Encoding UTF8
    Move-Item -LiteralPath $stagingPath -Destination $finalPath
    Write-Output "Backup finalized: $finalPath"
}

function Repair-ProfileRegistry {
    param(
        [Parameter(Mandatory)][string]$LiveRoot,
        [Parameter(Mandatory)][string]$SourceRoot
    )

    Stop-ChromeForRecovery
    $liveStatePath = Join-Path $LiveRoot 'Local State'
    $sourceStatePath = Join-Path $SourceRoot 'Local State'
    foreach ($path in $liveStatePath, $sourceStatePath) {
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
            throw "Local State is missing: $path"
        }
    }

    $live = Get-Content -LiteralPath $liveStatePath -Raw | ConvertFrom-Json
    $source = Get-Content -LiteralPath $sourceStatePath -Raw | ConvertFrom-Json
    $liveKey = [Convert]::FromBase64String($live.os_crypt.encrypted_key)
    $sourceKey = [Convert]::FromBase64String($source.os_crypt.encrypted_key)
    $hasher = [Security.Cryptography.SHA256]::Create()
    try {
        $liveHash = [BitConverter]::ToString($hasher.ComputeHash($liveKey)).Replace('-', '')
        $sourceHash = [BitConverter]::ToString($hasher.ComputeHash($sourceKey)).Replace('-', '')
    }
    finally {
        $hasher.Dispose()
    }
    if ($liveHash -ne $sourceHash) {
        throw 'Refusing registry repair: source and live Chrome encryption keys do not match.'
    }

    $changed = @()
    foreach ($profileName in 'Default', 'Profile 14', 'Profile 16', 'Profile 17') {
        $liveEntry = $live.profile.info_cache.PSObject.Properties[$profileName]
        $sourceEntry = $source.profile.info_cache.PSObject.Properties[$profileName]
        if ($null -eq $liveEntry -or $null -eq $sourceEntry) { continue }
        $liveUsername = [string]$liveEntry.Value.user_name
        $sourceUsername = [string]$sourceEntry.Value.user_name
        # Only fill a missing registration from a verified historical source; never replace
        # a currently registered account with a different one.
        if ([string]::IsNullOrWhiteSpace($liveUsername) -and -not [string]::IsNullOrWhiteSpace($sourceUsername)) {
            $liveEntry.Value = $sourceEntry.Value
            $changed += $profileName
        }
    }
    if ($changed.Count -eq 0) {
        Write-Output 'No missing Chrome profile registrations needed repair.'
        return
    }

    $stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
    $metadataBackup = Join-Path $LiveRoot "Local State.before_registry_repair_$stamp"
    Copy-Item -LiteralPath $liveStatePath -Destination $metadataBackup -Force
    try {
        $json = $live | ConvertTo-Json -Depth 100
        [System.IO.File]::WriteAllText($liveStatePath, $json, [System.Text.UTF8Encoding]::new($false))
    }
    catch {
        Copy-Item -LiteralPath $metadataBackup -Destination $liveStatePath -Force
        throw
    }
    Write-Output "Repaired missing registration metadata: $($changed -join ', ')"
    Write-Output "Metadata-only rollback copy: $metadataBackup"
}

if ($Mode -eq 'List') {
    if (-not (Test-Path -LiteralPath $BackupRoot)) {
        Write-Output "No backup root exists yet: $BackupRoot"
        exit 0
    }
    Get-ChildItem -LiteralPath $BackupRoot -Directory |
        Where-Object { $_.Name -match '^chrome_profile_\d{8}_\d{6}$' } |
        Sort-Object LastWriteTime -Descending |
        ForEach-Object {
            $manifest = Join-Path $_.FullName 'snapshot.json'
            [PSCustomObject]@{
                Snapshot = $_.FullName
                Created = $_.LastWriteTime
                ManifestPresent = Test-Path -LiteralPath $manifest -PathType Leaf
            }
        } | Format-Table -AutoSize
    exit 0
}

if ($Mode -eq 'Backup') {
    New-Snapshot -Source $ChromeUserData -DestinationRoot $BackupRoot | Out-Null
    exit 0
}

if ($Mode -eq 'Finalize') {
    if ([string]::IsNullOrWhiteSpace($Snapshot)) {
        throw 'Finalize requires the explicit path of an .incomplete snapshot directory.'
    }
    Complete-StagingSnapshot -Path $Snapshot | Out-Null
    exit 0
}

if ($Mode -eq 'RepairRegistry') {
    if (-not $ConfirmRegistryRepair) {
        throw 'Registry repair is intentionally blocked. Rerun with -ConfirmRegistryRepair and an explicit -Snapshot source root.'
    }
    if ([string]::IsNullOrWhiteSpace($Snapshot)) {
        throw 'Registry repair requires -Snapshot pointing to a historical Chrome User Data root.'
    }
    Repair-ProfileRegistry -LiveRoot $ChromeUserData -SourceRoot ((Resolve-Path -LiteralPath $Snapshot).Path)
    exit 0
}

if (-not $ConfirmRestore) {
    throw 'Restore is intentionally blocked. First inspect snapshots with -Mode List, then rerun with -Mode Restore -Snapshot <path> -ConfirmRestore.'
}
if ([string]::IsNullOrWhiteSpace($Snapshot)) {
    throw 'Restore requires an explicit -Snapshot path.'
}

$snapshotPath = (Resolve-Path -LiteralPath $Snapshot).Path
$snapshotProfiles = Test-Snapshot -Path $snapshotPath
Stop-ChromeForRecovery

# Preserve every live file this restore will replace before touching it.
$preRestore = New-Snapshot -Source $ChromeUserData -DestinationRoot $BackupRoot
foreach ($profile in $snapshotProfiles) {
    $liveProfile = Join-Path $ChromeUserData $profile.Name
    if (Test-Path -LiteralPath $liveProfile) {
        $quarantine = Join-Path $ChromeUserData ("$($profile.Name).restore_pending")
        if (Test-Path -LiteralPath $quarantine) {
            throw "Refusing to overwrite existing recovery path: $quarantine"
        }
        Move-Item -LiteralPath $liveProfile -Destination $quarantine
        try {
            Copy-Item -LiteralPath $profile.FullName -Destination $liveProfile -Recurse -Force
            Remove-Item -LiteralPath $quarantine -Recurse -Force
        }
        catch {
            if (Test-Path -LiteralPath $liveProfile) { Remove-Item -LiteralPath $liveProfile -Recurse -Force }
            Move-Item -LiteralPath $quarantine -Destination $liveProfile
            throw
        }
    }
    else {
        Copy-Item -LiteralPath $profile.FullName -Destination $liveProfile -Recurse -Force
    }
}
Copy-Item -LiteralPath (Join-Path $snapshotPath 'Local State') -Destination (Join-Path $ChromeUserData 'Local State') -Force
Write-Output "Restore complete from: $snapshotPath"
Write-Output "Pre-restore safety backup: $preRestore"
Write-Output 'Open Chrome normally. If a website requires a fresh sign-in, use its normal sign-in flow; encrypted cookies cannot be transferred to a different Windows account.'
