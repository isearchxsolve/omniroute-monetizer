param(
    [switch]$Once,
    [int]$IntervalSeconds = 2
)

$ErrorActionPreference = 'SilentlyContinue'
$log = 'D:\anonym\phone-health\battery-ac-guard.log'
$mutex = [Threading.Mutex]::new($false, 'Local\CodexBatteryAcGuard')
if (-not $mutex.WaitOne(0)) { exit 0 }

function Write-Log([string]$Message) {
    $directory = Split-Path -Parent $log
    if (-not (Test-Path -LiteralPath $directory)) {
        New-Item -ItemType Directory -Path $directory -Force | Out-Null
    }
    [IO.File]::AppendAllText($log, ('{0} {1}{2}' -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $Message, [Environment]::NewLine), [Text.UTF8Encoding]::new($false))
}

function Get-PowerState {
    $status = Get-CimInstance -Namespace root/wmi -ClassName BatteryStatus -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($null -eq $status) { return $null }
    [pscustomobject]@{
        Ac = [bool]$status.PowerOnLine
        Remaining_mWh = $status.RemainingCapacity
        ChargeRate_mW = $status.ChargeRate
        DischargeRate_mW = $status.DischargeRate
    }
}

try {
    $last = $null
    do {
        $current = Get-PowerState
        if ($null -ne $current) {
            if ($null -eq $last) {
                Write-Log ('BASELINE: AC={0}, remaining={1}mWh' -f $current.Ac, $current.Remaining_mWh)
            } elseif ($last.Ac -and -not $current.Ac) {
                Write-Log ('AC_LOSS: remaining={0}mWh; requesting normal Hibernate' -f $current.Remaining_mWh)
                & "$env:WINDIR\System32\shutdown.exe" /h
                Write-Log ('HIBERNATE_REQUEST_EXIT={0}' -f $LASTEXITCODE)
                break
            }
            $last = $current
        }
        if (-not $Once) { Start-Sleep -Seconds $IntervalSeconds }
    } while (-not $Once)
} finally {
    $mutex.ReleaseMutex()
    $mutex.Dispose()
}
