$ErrorActionPreference = 'Stop'
$monitorPath = Join-Path $PSScriptRoot '..\scripts\windows\usb_tethering_selfheal.ps1'
. $monitorPath

# Offline mocks: these tests never inspect or change the laptop's live routes.
$script:adapters = @()
$script:addresses = @{}
$script:metrics = @{}
$script:probes = @{}
$script:metricChanges = [Collections.Generic.List[string]]::new()
$script:messages = [Collections.Generic.List[string]]::new()

function Get-NetAdapter {
    param($ErrorAction)
    $script:adapters
}
function Get-NetIPAddress {
    param($InterfaceIndex, $AddressFamily, $ErrorAction)
    if ($script:addresses.ContainsKey([int]$InterfaceIndex)) {
        [pscustomobject]@{ IPAddress = $script:addresses[[int]$InterfaceIndex] }
    }
}
function Get-NetIPInterface {
    param($InterfaceIndex, $AddressFamily, $ErrorAction)
    if (-not $script:metrics.ContainsKey([int]$InterfaceIndex)) { throw 'Simulated missing interface metric' }
    [pscustomobject]@{ InterfaceMetric = $script:metrics[[int]$InterfaceIndex] }
}
function Set-NetIPInterface {
    param($InterfaceIndex, $AddressFamily, $AutomaticMetric, $InterfaceMetric, $ErrorAction)
    $script:metrics[[int]$InterfaceIndex] = [int]$InterfaceMetric
    $script:metricChanges.Add(('{0}:{1}' -f $InterfaceIndex, $InterfaceMetric))
}
function Test-InterfaceInternet {
    param($SourceAddress, $TimeoutMilliseconds)
    return [bool]$script:probes[$SourceAddress]
}
function Write-Log([string]$Message) { $script:messages.Add($Message) }

function Assert-Equal($Expected, $Actual, [string]$Description) {
    if ($Expected -ne $Actual) { throw "$Description : expected [$Expected], received [$Actual]" }
}
function Assert-Match([string]$Pattern, [string]$Actual, [string]$Description) {
    if ($Actual -notmatch $Pattern) { throw "$Description : expected pattern [$Pattern], received [$Actual]" }
}
function Test-Case([string]$Name, [scriptblock]$Body) {
    & $Body
    Write-Output ('PASS: ' + $Name)
}
function Reset-Case {
    $script:adapters = @(
        [pscustomobject]@{ Name = 'Wi-Fi'; InterfaceDescription = 'Intel Wireless'; Status = 'Up'; ifIndex = 21 },
        [pscustomobject]@{ Name = 'Ethernet 6'; InterfaceDescription = 'Remote NDIS based Internet Sharing Device'; Status = 'Up'; ifIndex = 10 }
    )
    $script:addresses = @{ 21 = '192.168.1.2'; 10 = '192.168.179.118' }
    $script:metrics = @{ 21 = 10; 10 = 25 }
    $script:probes = @{ '192.168.1.2' = $true; '192.168.179.118' = $true }
    $script:metricChanges.Clear()
    $script:messages.Clear()
    $script:lastFailoverStatus = ''
    $script:wifiFailureSamples = 0
    $script:wifiSuccessSamples = 0
}

Test-Case 'Healthy Wi-Fi stays preferred without changing metrics' {
    Reset-Case
    Update-InternetFailover
    Assert-Equal 0 $script:metricChanges.Count 'Metric change count'
    Assert-Match '^HEALTHY: Wi-Fi Internet is reachable and remains' $script:messages[0] 'Healthy state'
}
Test-Case 'One Wi-Fi failure is held for confirmation' {
    Reset-Case
    $script:probes['192.168.1.2'] = $false
    Update-InternetFailover
    Assert-Equal 0 $script:metricChanges.Count 'Metric change count after one failure'
    Assert-Match '^WAIT: Wi-Fi Internet failure sample 1/2' $script:messages[0] 'First-failure state'
}
Test-Case 'Two Wi-Fi failures promote only an independently working tether path' {
    Reset-Case
    $script:probes['192.168.1.2'] = $false
    Update-InternetFailover
    Update-InternetFailover
    Assert-Equal 2 $script:metricChanges.Count 'Metric change count after confirmation'
    Assert-Equal 50 $script:metrics[21] 'Wi-Fi fallback metric'
    Assert-Equal 5 $script:metrics[10] 'Tether preferred metric'
    Assert-Match '^OK: Wi-Fi Internet failed twice; USB tether was Internet-verified' $script:messages[$script:messages.Count - 1] 'Promotion state'
}
Test-Case 'A broken tether path is never promoted' {
    Reset-Case
    $script:probes['192.168.1.2'] = $false
    $script:probes['192.168.179.118'] = $false
    Update-InternetFailover
    Update-InternetFailover
    Assert-Equal 0 $script:metricChanges.Count 'Metric change count with broken tether'
    Assert-Match '^WAIT: Wi-Fi failed, but USB tether Internet was not independently verified' $script:messages[$script:messages.Count - 1] 'Tether verification gate'
}
Test-Case 'A disconnected Wi-Fi adapter immediately prepares a working tether route' {
    Reset-Case
    $script:adapters = @($script:adapters[1])
    Update-InternetFailover
    Assert-Equal 1 $script:metricChanges.Count 'Metric change count when Wi-Fi is absent'
    Assert-Equal 5 $script:metrics[10] 'Tether metric when Wi-Fi is absent'
}
Test-Case 'Two healthy Wi-Fi samples restore Wi-Fi after tether preference' {
    Reset-Case
    $script:metrics[21] = 50
    $script:metrics[10] = 5
    Update-InternetFailover
    Assert-Equal 0 $script:metricChanges.Count 'Metric changes after first recovery sample'
    Update-InternetFailover
    Assert-Equal 2 $script:metricChanges.Count 'Metric changes after second recovery sample'
    Assert-Equal 10 $script:metrics[21] 'Restored Wi-Fi metric'
    Assert-Equal 25 $script:metrics[10] 'Restored tether standby metric'
    Assert-Match '^OK: Wi-Fi Internet recovered twice; Wi-Fi is preferred again' $script:messages[$script:messages.Count - 1] 'Recovery state'
}

Write-Output 'PASS: 6 offline route-failover regression cases; no adapter, route, ADB, or network calls were made.'
