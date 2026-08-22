[CmdletBinding()]
param(
    [ValidateSet('Backup', 'List', 'Restore')]
    [string]$Mode = 'Backup',

    [string]$ChromeUserData = (Join-Path $env:LOCALAPPDATA 'Google\Chrome\User Data'),

    [string]$BackupRoot = 'D:\omniroute-backups\chrome-profiles',

    [string]$Snapshot,

    [switch]$ConfirmRestore
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
        Set-Content -LiteralPath (Join-Path $staging 'snapshot.json') -Value $manifest -Encoding utf8NoBOM
        Move-Item -LiteralPath $staging -Destination $destination
        Write-Output "Backup complete: $destination"
        return $destination
    }
    catch {
        Write-Warning "Backup was not finalized; incomplete copy preserved at: $staging"
        throw
    }
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
