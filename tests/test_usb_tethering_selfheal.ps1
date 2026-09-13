$ErrorActionPreference = 'Stop'
$monitorPath = Join-Path $PSScriptRoot '..\scripts\windows\usb_tethering_selfheal.ps1'
. $monitorPath

# All hardware calls and sleeps are replaced. Tests never invoke adb or query adapters.
$script:adapterStates = [Collections.Queue]::new()
$script:commands = [Collections.Generic.List[string]]::new()
$script:messages = [Collections.Generic.List[string]]::new()
$script:captureMode = 'off'
function Get-NetAdapter {
    param($ErrorAction)
    if ($script:adapterStates.Count -gt 1) {
        $state = $script:adapterStates.Dequeue()
    } else {
        $state = $script:adapterStates.Peek()
    }
    if ($state -eq 'Unknown') { throw 'Simulated adapter query failure' }
    [pscustomobject]@{ Status = $state; InterfaceDescription = 'Remote NDIS Compatible Device' }
}
function Start-Sleep { param($Seconds) }
function Write-Log([string]$Message) { $script:messages.Add($Message) }
function Invoke-Adb {
    param([string[]]$Arguments, [int]$TimeoutSeconds = 10)
    $script:commands.Add(($Arguments -join ' '))
    $success = $true
    $output = ''
    if ($Arguments[0] -eq 'get-state') { $output = 'device' }
    if ($Arguments[0] -eq 'shell' -and $Arguments[1] -eq 'uiautomator') {
        if ($script:captureMode -eq 'dump-failed') { $success = $false }
    }
    if ($Arguments[0] -eq 'pull') {
        $attributes = 'enabled="true" clickable="true" checkable="true" checked="false"'
        if ($script:captureMode -eq 'on') { $attributes = $attributes.Replace('checked="false"', 'checked="true"') }
        if ($script:captureMode -eq 'missing-checked') { $attributes = $attributes.Replace(' checked="false"', '') }
        if ($script:captureMode -eq 'disabled') { $attributes = $attributes.Replace('enabled="true"', 'enabled="false"') }
        $node = '<node content-desc="USB tethering" bounds="[10,20][110,80]" ' + $attributes + ' />'
        if ($script:captureMode -eq 'ambiguous') { $node += $node }
        [IO.File]::WriteAllText($Arguments[2], '<hierarchy>' + $node + '</hierarchy>')
        # A failed download must be rejected even if it left a parseable file behind.
        if ($script:captureMode -eq 'pull-failed') { $success = $false }
    }
    [pscustomobject]@{ Success = $success; Output = $output; Reason = 'simulated result' }
}
function Reset-Case([string[]]$States = @('Down'), [string]$Mode = 'off') {
    $script:adapterStates.Clear()
    foreach ($state in $States) { $script:adapterStates.Enqueue($state) }
    $script:commands.Clear()
    $script:messages.Clear()
    $script:captureMode = $Mode
    $script:lastStatus = ''
    $script:lastRecovery = [datetime]::MinValue
}
function Assert-Equal($Expected, $Actual, [string]$Description) {
    if ($Expected -ne $Actual) { throw "$Description : expected [$Expected], received [$Actual]" }
}
function Assert-NoTap {
    Assert-Equal 0 @($script:commands | Where-Object { $_ -like 'shell input tap *' }).Count 'No phone tap'
}
function Test-Case([string]$Name, [scriptblock]$Body) {
    & $Body
    Write-Output ('PASS: ' + $Name)
}

$originalTemp = $env:TEMP
$testTemp = Join-Path $originalTemp ('tether-offline-test-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $testTemp | Out-Null
$env:TEMP = $testTemp
try {
    Test-Case 'Healthy adapter is a no-op, including no ADB commands' {
        Reset-Case -States @('Up')
        Restore-UsbTethering
        Assert-Equal 0 $script:commands.Count 'ADB invocation count'
        Assert-Equal 1 $script:messages.Count 'Healthy state logged'
        Restore-UsbTethering
        Assert-Equal 1 $script:messages.Count 'Unchanged healthy state is not repeated'
    }
    Test-Case 'Adapter query failure is Unknown, never a recovery trigger' {
        Reset-Case -States @('Unknown')
        Restore-UsbTethering
        Assert-Equal 0 $script:commands.Count 'ADB invocation count'
    }
    Test-Case 'Transient Down recovers during debounce without phone action' {
        Reset-Case -States @('Down', 'Up')
        Restore-UsbTethering
        Assert-Equal 0 $script:commands.Count 'ADB invocation count'
    }
    Test-Case 'Failed dump cannot reuse a stale XML file' {
        Reset-Case -Mode 'dump-failed'
        $stale = Join-Path $env:TEMP 'codex-tether-state.xml'
        [IO.File]::WriteAllText($stale, '<hierarchy><node content-desc="USB tethering" enabled="true" clickable="true" checkable="true" checked="false" bounds="[10,20][110,80]" /></hierarchy>')
        Restore-UsbTethering
        Assert-NoTap
        Assert-Equal 0 @($script:commands | Where-Object { $_ -like 'pull *' }).Count 'No pull after failed dump'
        Assert-Equal $true (Test-Path -LiteralPath $stale) 'Legacy snapshot was not used or deleted'
    }
    Test-Case 'Failed pull is rejected even if a parseable current file exists' {
        Reset-Case -Mode 'pull-failed'
        Restore-UsbTethering
        Assert-NoTap
    }
    Test-Case 'Confirmed Down and explicit Off permits exactly one tap then verifies' {
        Reset-Case -States @('Down', 'Down', 'Down', 'Down', 'Up')
        Restore-UsbTethering
        Assert-Equal 1 @($script:commands | Where-Object { $_ -eq 'shell input tap 60 50' }).Count 'Tap count and coordinates'
        Assert-Equal 1 @($script:messages | Where-Object { $_ -like 'OK: USB tethering restored*' }).Count 'Restoration verified'
        Assert-Equal 0 @(Get-ChildItem -LiteralPath $env:TEMP -Filter 'codex-tether-*.xml' | Where-Object {
            $_.Name -match '^codex-tether-[0-9a-f]{32}\.xml$'
        }).Count 'Unique capture cleaned up'
    }
    Test-Case 'Already-On switch is never toggled Off' {
        Reset-Case -Mode 'on'
        Restore-UsbTethering
        Assert-NoTap
    }
    Test-Case 'Missing checked attribute is not treated as Off' {
        Reset-Case -Mode 'missing-checked'
        Restore-UsbTethering
        Assert-NoTap
    }
    Test-Case 'Disabled switch is never tapped' {
        Reset-Case -Mode 'disabled'
        Restore-UsbTethering
        Assert-NoTap
    }
    Test-Case 'Ambiguous duplicate switches fail closed' {
        Reset-Case -Mode 'ambiguous'
        Restore-UsbTethering
        Assert-NoTap
    }
    Test-Case 'Adapter recovers before tap, so saved coordinates are not used' {
        Reset-Case -States @('Down', 'Down', 'Down', 'Up')
        Restore-UsbTethering
        Assert-NoTap
    }
    Test-Case 'Adapter query fails before tap, so phone remains untouched' {
        Reset-Case -States @('Down', 'Down', 'Down', 'Unknown')
        Restore-UsbTethering
        Assert-NoTap
    }
    Test-Case 'Cooldown prevents repeated Android settings launches' {
        Reset-Case -Mode 'on'
        Restore-UsbTethering
        $firstCount = $script:commands.Count
        Restore-UsbTethering
        Assert-Equal $firstCount $script:commands.Count 'No extra ADB calls during cooldown'
    }
    Test-Case 'Separate attempts use separate remote and local snapshots' {
        Reset-Case -Mode 'on'
        Restore-UsbTethering
        $script:lastRecovery = [datetime]::MinValue
        Restore-UsbTethering
        $pulls = @($script:commands | Where-Object { $_ -like 'pull *' })
        Assert-Equal 2 $pulls.Count 'Two captures'
        Assert-Equal $false ($pulls[0] -eq $pulls[1]) 'Fresh paths for both captures'
    }
    Write-Output 'PASS: 14 offline regression cases; no hardware calls or real sleeps.'
} finally {
    $env:TEMP = $originalTemp
    # Only test-owned files; no recursive directory deletion.
    Get-ChildItem -LiteralPath $testTemp -File | Remove-Item
    Remove-Item -LiteralPath $testTemp
}
