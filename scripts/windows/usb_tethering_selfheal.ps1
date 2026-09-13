param(
    [switch]$Once,
    [int]$IntervalSeconds = 30
)

$ErrorActionPreference = 'SilentlyContinue'
$adb = 'D:\anonym\platform-tools\adb.exe'
$log = 'D:\anonym\phone-health\usb-tethering-selfheal.log'
$mutex = [Threading.Mutex]::new($false, 'Local\CodexUsbTetheringSelfHeal')

if (-not $mutex.WaitOne(0)) { exit 0 }

function Write-Log([string]$Message) {
    $directory = Split-Path -Parent $log
    if (-not (Test-Path -LiteralPath $directory)) {
        New-Item -ItemType Directory -Path $directory -Force | Out-Null
    }
    $line = '{0} {1}{2}' -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $Message, [Environment]::NewLine
    [IO.File]::AppendAllText($log, $line, [Text.UTF8Encoding]::new($false))
}

function Test-AdbOnline {
    if (-not (Test-Path -LiteralPath $adb)) { return $false }
    $state = (& $adb get-state 2>$null | Out-String).Trim()
    return $state -eq 'device'
}

function Test-RndisOnline {
    $adapter = Get-NetAdapter | Where-Object {
        $_.Status -eq 'Up' -and $_.InterfaceDescription -match 'Remote NDIS|RNDIS|Android.*Ethernet'
    } | Select-Object -First 1
    return $null -ne $adapter
}

function Restore-UsbTethering {
    if (-not (Test-AdbOnline)) {
        Write-Log 'WAIT: ADB is unavailable; cable, USB debugging, or phone authorization needs attention.'
        return
    }

    if (Test-RndisOnline) { return }

    Write-Log 'RECOVERY: RNDIS is down while ADB is online; opening Android tether settings.'
    & $adb shell am start -a android.settings.TETHER_SETTINGS 2>$null | Out-Null
    Start-Sleep -Seconds 2

    $remoteXml = '/sdcard/codex-tether-state.xml'
    $localXml = Join-Path $env:TEMP 'codex-tether-state.xml'
    & $adb shell uiautomator dump $remoteXml 2>$null | Out-Null
    & $adb pull $remoteXml $localXml 2>$null | Out-Null
    if (-not (Test-Path -LiteralPath $localXml)) {
        Write-Log 'WAIT: Android UI state was unavailable, usually because the phone is locked.'
        return
    }

    try { [xml]$ui = Get-Content -LiteralPath $localXml -Raw } catch {
        Write-Log 'WAIT: Android UI state could not be parsed.'
        return
    }

    $switch = $ui.SelectNodes('//node') | Where-Object {
        $_.'content-desc' -match '^USB tethering' -and $_.clickable -eq 'true'
    } | Select-Object -First 1
    if ($null -eq $switch) {
        Write-Log 'WAIT: USB tethering switch was not visible; unlock the phone once.'
        return
    }

    if ($switch.checked -ne 'true' -and $switch.bounds -match '^\[(\d+),(\d+)\]\[(\d+),(\d+)\]$') {
        $x = [int](([int]$matches[1] + [int]$matches[3]) / 2)
        $y = [int](([int]$matches[2] + [int]$matches[4]) / 2)
        & $adb shell input tap $x $y 2>$null | Out-Null
        Start-Sleep -Seconds 5
    }

    if ((Test-AdbOnline) -and (Test-RndisOnline)) {
        Write-Log 'OK: USB tethering restored; RNDIS and ADB are both online.'
    } else {
        Write-Log 'WAIT: Automatic restore did not complete; unlock the phone and leave USB tethering allowed.'
    }
}

try {
    do {
        Restore-UsbTethering
        if (-not $Once) { Start-Sleep -Seconds $IntervalSeconds }
    } while (-not $Once)
} finally {
    $mutex.ReleaseMutex()
    $mutex.Dispose()
}
