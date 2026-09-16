[CmdletBinding()]
param(
    [switch]$DoNotStart
)

$ErrorActionPreference = 'Stop'
$taskName = 'Codex USB Tether Failover'
$monitorPath = Join-Path $PSScriptRoot 'usb_tethering_selfheal.ps1'
$identity = '{0}\{1}' -f $env:USERDOMAIN, $env:USERNAME

if (-not (Test-Path -LiteralPath $monitorPath -PathType Leaf)) {
    throw "The tether monitor was not found at $monitorPath"
}
$principal = [Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'Administrator rights are required to install the automatic tether-failover task.'
}

$powerShell = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
$arguments = '-NoLogo -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "{0}" -IntervalSeconds 15' -f $monitorPath
$action = New-ScheduledTaskAction -Execute $powerShell -Argument $arguments
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $identity
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -MultipleInstances IgnoreNew -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit ([TimeSpan]::Zero)
$taskPrincipal = New-ScheduledTaskPrincipal -UserId $identity -LogonType Interactive -RunLevel Highest

Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -Principal $taskPrincipal -Description 'Keeps Wi-Fi preferred while healthy and promotes an independently verified USB tether route after two Wi-Fi Internet failures.' -Force | Out-Null
if (-not $DoNotStart) {
    Start-ScheduledTask -TaskName $taskName
}

$task = Get-ScheduledTask -TaskName $taskName
[pscustomobject]@{
    TaskName = $task.TaskName
    State = $task.State
    RunLevel = $task.Principal.RunLevel
    Action = ($task.Actions | Select-Object -First 1).Execute
    Arguments = ($task.Actions | Select-Object -First 1).Arguments
}
