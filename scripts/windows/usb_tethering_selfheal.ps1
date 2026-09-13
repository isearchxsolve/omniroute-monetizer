param(
    [switch]$Once,
    [ValidateRange(10, 3600)]
    [int]$IntervalSeconds = 30
)

$adb = 'D:\anonym\platform-tools\adb.exe'
$log = 'D:\anonym\phone-health\usb-tethering-selfheal.log'
$script:lastStatus = ''
$script:lastRecovery = [datetime]::MinValue
$recoveryCooldownSeconds = 120

function Write-Log([string]$Message) {
    try {
        $directory = Split-Path -Parent $log
        if (-not (Test-Path -LiteralPath $directory)) {
            New-Item -ItemType Directory -Path $directory -Force -ErrorAction Stop | Out-Null
        }
        $line = '{0} {1}{2}' -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $Message, [Environment]::NewLine
        [IO.File]::AppendAllText($log, $line, [Text.UTF8Encoding]::new($false))
    } catch {
        Write-Warning 'USB tether monitor could not write its log.'
    }
}

function Write-State([string]$Message) {
    if ($script:lastStatus -ne $Message) {
        Write-Log $Message
        $script:lastStatus = $Message
    }
}

function Invoke-Adb {
    param([string[]]$Arguments, [int]$TimeoutSeconds = 10)
    $process = [Diagnostics.Process]::new()
    try {
        $process.StartInfo.FileName = $adb
        # Windows PowerShell 5.1 has no ProcessStartInfo.ArgumentList.
        $process.StartInfo.Arguments = ($Arguments | ForEach-Object {
            '"' + ($_ -replace '(\\*)"', '$1$1\"' -replace '(\\+)$', '$1$1') + '"'
        }) -join ' '
        $process.StartInfo.UseShellExecute = $false
        $process.StartInfo.CreateNoWindow = $true
        $process.StartInfo.RedirectStandardOutput = $true
        $process.StartInfo.RedirectStandardError = $true
        if (-not $process.Start()) { throw 'ADB did not start.' }
        $stdout = $process.StandardOutput.ReadToEndAsync()
        $stderr = $process.StandardError.ReadToEndAsync()
        if (-not $process.WaitForExit($TimeoutSeconds * 1000)) {
            $process.Kill() # Only this monitor's timed-out child, never the ADB server.
            return [pscustomobject]@{ Success = $false; Output = ''; Reason = 'timeout' }
        }
        if (-not $stdout.Wait(1000) -or -not $stderr.Wait(1000)) {
            return [pscustomobject]@{ Success = $false; Output = ''; Reason = 'output timeout' }
        }
        return [pscustomobject]@{
            Success = ($process.ExitCode -eq 0)
            Output = $stdout.Result
            Reason = 'exit ' + $process.ExitCode
        }
    } catch {
        return [pscustomobject]@{ Success = $false; Output = ''; Reason = 'command unavailable' }
    } finally {
        $process.Dispose()
    }
}

function Get-RndisState {
    try {
        $adapter = Get-NetAdapter -ErrorAction Stop | Where-Object {
            $_.Status -eq 'Up' -and $_.InterfaceDescription -match 'Remote NDIS|RNDIS|Android.*Ethernet'
        } | Select-Object -First 1
        if ($null -ne $adapter) { return 'Up' }
        return 'Down'
    } catch {
        return 'Unknown'
    }
}

function Restore-UsbTethering {
    $state = Get-RndisState
    if ($state -eq 'Up') {
        Write-State 'HEALTHY: RNDIS is up; no phone action needed.'
        return
    }
    if ($state -ne 'Down') {
        Write-State 'WAIT: Adapter query unavailable; leaving the phone untouched.'
        return
    }
    if (((Get-Date) - $script:lastRecovery).TotalSeconds -lt $recoveryCooldownSeconds) {
        Write-State 'WAIT: Recovery cooldown; leaving the phone untouched.'
        return
    }
    # Allow Windows enumeration to settle before treating one Down sample as a fault.
    Start-Sleep -Seconds 2
    if ((Get-RndisState) -ne 'Down') {
        Write-State 'WAIT: RNDIS recovered or its state became unknown during confirmation.'
        return
    }
    $connection = Invoke-Adb -Arguments @('get-state')
    if (-not $connection.Success -or $connection.Output.Trim() -ne 'device') {
        Write-State 'WAIT: ADB unavailable or unauthorized; leaving the phone untouched.'
        return
    }
    if ((Get-RndisState) -ne 'Down') { return }
    $script:lastRecovery = Get-Date
    Write-State 'RECOVERY: RNDIS confirmed down with ADB online; checking Android tether settings.'
    $opened = Invoke-Adb -Arguments @('shell', 'am', 'start', '-a', 'android.settings.TETHER_SETTINGS')
    if (-not $opened.Success) {
        Write-State ('WAIT: Could not open tether settings (' + $opened.Reason + ').')
        return
    }
    Start-Sleep -Seconds 2
    # A failed dump/pull must never reuse a previous attempt's coordinates or checked state.
    $captureName = 'codex-tether-' + [guid]::NewGuid().ToString('N') + '.xml'
    $remoteXml = '/sdcard/' + $captureName
    $localXml = Join-Path $env:TEMP $captureName
    try {
        $dump = Invoke-Adb -Arguments @('shell', 'uiautomator', 'dump', $remoteXml) -TimeoutSeconds 15
        if (-not $dump.Success) {
            Write-State ('WAIT: Fresh Android UI dump failed (' + $dump.Reason + '); no tap.')
            return
        }
        $pull = Invoke-Adb -Arguments @('pull', $remoteXml, $localXml)
        if (-not $pull.Success -or -not (Test-Path -LiteralPath $localXml)) {
            Write-State 'WAIT: Fresh Android UI download failed; no tap.'
            return
        }
        try { [xml]$ui = Get-Content -LiteralPath $localXml -Raw -ErrorAction Stop } catch {
            Write-State 'WAIT: Fresh Android UI could not be parsed; no tap.'
            return
        }
        $switches = @($ui.SelectNodes('//node') | Where-Object {
            $_.'content-desc' -match '^USB tethering' -and
            $_.enabled -eq 'true' -and $_.clickable -eq 'true' -and
            $_.checkable -eq 'true' -and $_.checked -eq 'false'
        })
        if ($switches.Count -ne 1) {
            Write-State 'WAIT: No unique, enabled USB tether switch explicitly Off; no tap.'
            return
        }
        $switch = $switches[0]
        if ($switch.bounds -notmatch '^\[(\d+),(\d+)\]\[(\d+),(\d+)\]$') { return }
        $x = [int](([int]$matches[1] + [int]$matches[3]) / 2)
        $y = [int](([int]$matches[2] + [int]$matches[4]) / 2)
        if ((Get-RndisState) -ne 'Down') {
            Write-State 'WAIT: RNDIS recovered or its state became unknown before tap; no tap.'
            return
        }
        $tap = Invoke-Adb -Arguments @('shell', 'input', 'tap', [string]$x, [string]$y)
        if (-not $tap.Success) {
            Write-State ('WAIT: Tether switch tap failed (' + $tap.Reason + ').')
            return
        }
        Start-Sleep -Seconds 5
        $connection = Invoke-Adb -Arguments @('get-state')
        if ((Get-RndisState) -eq 'Up' -and $connection.Success -and $connection.Output.Trim() -eq 'device') {
            Write-State 'OK: USB tethering restored; RNDIS and ADB are both online.'
        } else {
            Write-State 'WAIT: Restore not confirmed; retry deferred by cooldown.'
        }
    } finally {
        Remove-Item -LiteralPath $localXml -ErrorAction SilentlyContinue
        Invoke-Adb -Arguments @('shell', 'rm', '-f', $remoteXml) -TimeoutSeconds 5 | Out-Null
    }
}

# Dot-sourcing defines functions for offline regression tests without starting the monitor.
if ($MyInvocation.InvocationName -eq '.') { return }
$mutex = [Threading.Mutex]::new($false, 'Local\CodexUsbTetheringSelfHeal')
$ownsMutex = $false
try {
    try { $ownsMutex = $mutex.WaitOne(0) } catch [Threading.AbandonedMutexException] {
        $ownsMutex = $true
    }
    if (-not $ownsMutex) { return }
    Write-Log 'START: USB tether monitor; confirmed-down recovery, fresh UI, 120-second cooldown.'
    do {
        try { Restore-UsbTethering } catch {
            Write-State 'WAIT: Unexpected monitor error; deferring recovery.'
        }
        if (-not $Once) { Start-Sleep -Seconds $IntervalSeconds }
    } while (-not $Once)
} finally {
    if ($ownsMutex) { $mutex.ReleaseMutex() }
    $mutex.Dispose()
}
