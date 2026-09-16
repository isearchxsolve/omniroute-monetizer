param(
    [switch]$Once,
    [ValidateRange(10, 3600)]
    [int]$IntervalSeconds = 15
)

$adb = 'D:\anonym\platform-tools\adb.exe'
$log = 'D:\anonym\phone-health\usb-tethering-selfheal.log'
$script:lastStatus = ''
$script:lastFailoverStatus = ''
$script:lastRecovery = [datetime]::MinValue
$script:wifiFailureSamples = 0
$script:wifiSuccessSamples = 0
$recoveryCooldownSeconds = 120
$wifiFailureSamplesRequired = 2
$wifiRecoverySamplesRequired = 2

# These are intentionally limited to the two adapters this monitor owns.  Lower
# IPv4 metrics win when Windows has matching default routes.
$wifiPreferredMetric = 10
$tetherStandbyMetric = 25
$tetherPreferredMetric = 5
$wifiFallbackMetric = 50

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

function Write-FailoverState([string]$Message) {
    if ($script:lastFailoverStatus -ne $Message) {
        Write-Log $Message
        $script:lastFailoverStatus = $Message
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

function Get-RndisAdapter {
    $matches = @(Get-NetAdapter -ErrorAction Stop | Where-Object {
        $_.Status -eq 'Up' -and $_.InterfaceDescription -match 'Remote NDIS|RNDIS|Android.*Ethernet'
    })
    if ($matches.Count -gt 0) { return $matches[0] }
    return $null
}

function Get-RndisState {
    try {
        if ($null -ne (Get-RndisAdapter)) { return 'Up' }
        return 'Down'
    } catch {
        return 'Unknown'
    }
}

function Get-WifiAdapter {
    $matches = @(Get-NetAdapter -ErrorAction Stop | Where-Object {
        $_.Status -eq 'Up' -and (
            $_.Name -match 'Wi-?Fi|Wireless|802\.11' -or
            $_.InterfaceDescription -match 'Wi-?Fi|Wireless|802\.11'
        )
    })
    if ($matches.Count -gt 0) { return $matches[0] }
    return $null
}

function Get-AdapterIpv4Address {
    param([object]$Adapter)
    if ($null -eq $Adapter -or $null -eq $Adapter.ifIndex) { return $null }
    $addresses = @(Get-NetIPAddress -InterfaceIndex ([int]$Adapter.ifIndex) -AddressFamily IPv4 -ErrorAction Stop |
        Where-Object {
            $_.IPAddress -and
            $_.IPAddress -notmatch '^(0\.|127\.|169\.254\.)'
        })
    if ($addresses.Count -gt 0) { return [string]$addresses[0].IPAddress }
    return $null
}

function Test-InterfaceInternet {
    param(
        [string]$SourceAddress,
        [ValidateRange(1000, 15000)]
        [int]$TimeoutMilliseconds = 4000
    )
    if ([string]::IsNullOrWhiteSpace($SourceAddress)) { return $false }
    foreach ($destination in @('1.1.1.1', '8.8.8.8')) {
        $client = $null
        try {
            $client = [Net.Sockets.TcpClient]::new([Net.Sockets.AddressFamily]::InterNetwork)
            $source = [Net.IPAddress]::Parse($SourceAddress)
            $client.Client.Bind([Net.IPEndPoint]::new($source, 0))
            $connect = $client.ConnectAsync($destination, 443)
            if ($connect.Wait($TimeoutMilliseconds) -and $client.Connected) {
                return $true
            }
        } catch {
            # Try the independent second endpoint before treating the path as down.
        } finally {
            if ($null -ne $client) { $client.Dispose() }
        }
    }
    return $false
}

function Get-RouteMode {
    param([object]$WifiAdapter, [object]$TetherAdapter)
    if ($null -eq $WifiAdapter -or $null -eq $TetherAdapter) { return 'Unknown' }
    try {
        $wifi = @(Get-NetIPInterface -InterfaceIndex ([int]$WifiAdapter.ifIndex) -AddressFamily IPv4 -ErrorAction Stop)[0]
        $tether = @(Get-NetIPInterface -InterfaceIndex ([int]$TetherAdapter.ifIndex) -AddressFamily IPv4 -ErrorAction Stop)[0]
        if ([int]$tether.InterfaceMetric -lt [int]$wifi.InterfaceMetric) { return 'Tether' }
        return 'Wifi'
    } catch {
        return 'Unknown'
    }
}

function Set-RouteMode {
    param(
        [ValidateSet('Wifi', 'Tether')]
        [string]$Mode,
        [object]$WifiAdapter,
        [object]$TetherAdapter
    )
    if ($Mode -eq 'Tether') {
        if ($null -ne $WifiAdapter) {
            Set-NetIPInterface -InterfaceIndex ([int]$WifiAdapter.ifIndex) -AddressFamily IPv4 -AutomaticMetric Disabled -InterfaceMetric $wifiFallbackMetric -ErrorAction Stop
        }
        Set-NetIPInterface -InterfaceIndex ([int]$TetherAdapter.ifIndex) -AddressFamily IPv4 -AutomaticMetric Disabled -InterfaceMetric $tetherPreferredMetric -ErrorAction Stop
        return
    }
    # Raise tether first so a successful Wi-Fi recovery is the only path that becomes preferred.
    Set-NetIPInterface -InterfaceIndex ([int]$TetherAdapter.ifIndex) -AddressFamily IPv4 -AutomaticMetric Disabled -InterfaceMetric $tetherStandbyMetric -ErrorAction Stop
    Set-NetIPInterface -InterfaceIndex ([int]$WifiAdapter.ifIndex) -AddressFamily IPv4 -AutomaticMetric Disabled -InterfaceMetric $wifiPreferredMetric -ErrorAction Stop
}

function Update-InternetFailover {
    $wifi = $null
    try {
        $wifi = Get-WifiAdapter
    } catch {
        Write-FailoverState 'WAIT: Wi-Fi adapter query unavailable; IPv4 route metrics were left unchanged.'
        return
    }
    $tether = $null
    try { $tether = Get-RndisAdapter } catch { $tether = $null }

    $wifiAddress = Get-AdapterIpv4Address $wifi
    $wifiOnline = $false
    if ($null -ne $wifi -and $null -ne $wifiAddress) {
        $wifiOnline = Test-InterfaceInternet -SourceAddress $wifiAddress
    }

    if ($wifiOnline) {
        $script:wifiFailureSamples = 0
        $script:wifiSuccessSamples++
        if ($null -eq $tether) {
            Write-FailoverState 'HEALTHY: Wi-Fi Internet is reachable; USB tether adapter is not present.'
            return
        }
        $mode = Get-RouteMode -WifiAdapter $wifi -TetherAdapter $tether
        if ($mode -eq 'Tether') {
            if ($script:wifiSuccessSamples -lt $wifiRecoverySamplesRequired) {
                Write-FailoverState ('WAIT: Wi-Fi recovery sample {0}/{1}; keeping the proven USB tether route.' -f $script:wifiSuccessSamples, $wifiRecoverySamplesRequired)
                return
            }
            try {
                Set-RouteMode -Mode Wifi -WifiAdapter $wifi -TetherAdapter $tether
                Write-FailoverState 'OK: Wi-Fi Internet recovered twice; Wi-Fi is preferred again and USB tether remains standby.'
            } catch {
                Write-FailoverState 'WAIT: Wi-Fi recovered, but route metrics need an elevated monitor; no route was claimed changed.'
            }
            return
        }
        if ($mode -eq 'Unknown') {
            Write-FailoverState 'WAIT: Wi-Fi is reachable, but IPv4 route metrics could not be read; leaving them unchanged.'
            return
        }
        Write-FailoverState 'HEALTHY: Wi-Fi Internet is reachable and remains the preferred IPv4 route.'
        return
    }

    $script:wifiSuccessSamples = 0
    if ($null -eq $wifi) {
        $script:wifiFailureSamples = $wifiFailureSamplesRequired
    } else {
        $script:wifiFailureSamples++
    }
    if ($null -eq $tether) {
        Write-FailoverState 'WAIT: Wi-Fi has no usable Internet path and the USB tether adapter is absent; no route change.'
        return
    }
    $tetherAddress = Get-AdapterIpv4Address $tether
    if ($null -eq $tetherAddress -or -not (Test-InterfaceInternet -SourceAddress $tetherAddress)) {
        Write-FailoverState 'WAIT: Wi-Fi failed, but USB tether Internet was not independently verified; no route change.'
        return
    }
    if ($script:wifiFailureSamples -lt $wifiFailureSamplesRequired) {
        Write-FailoverState ('WAIT: Wi-Fi Internet failure sample {0}/{1}; holding its priority until confirmed.' -f $script:wifiFailureSamples, $wifiFailureSamplesRequired)
        return
    }
    $mode = Get-RouteMode -WifiAdapter $wifi -TetherAdapter $tether
    if ($mode -eq 'Tether') {
        Write-FailoverState 'OK: Wi-Fi Internet is unavailable; the independently verified USB tether route remains preferred.'
        return
    }
    try {
        Set-RouteMode -Mode Tether -WifiAdapter $wifi -TetherAdapter $tether
        Write-FailoverState 'OK: Wi-Fi Internet failed twice; USB tether was Internet-verified and is now the preferred IPv4 route.'
    } catch {
        Write-FailoverState 'WAIT: USB tether works, but changing route metrics needs an elevated monitor; routes were left unchanged.'
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
    Write-Log 'START: USB tether monitor; confirmed-down recovery plus two-sample Wi-Fi-to-tether IPv4 failover.'
    do {
        try {
            Restore-UsbTethering
        } catch {
            Write-State 'WAIT: Unexpected monitor error; deferring recovery.'
        }
        try {
            Update-InternetFailover
        } catch {
            Write-FailoverState 'WAIT: Unexpected failover-monitor error; IPv4 route metrics were left unchanged.'
        }
        if (-not $Once) { Start-Sleep -Seconds $IntervalSeconds }
    } while (-not $Once)
} finally {
    if ($ownsMutex) { $mutex.ReleaseMutex() }
    $mutex.Dispose()
}
