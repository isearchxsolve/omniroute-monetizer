$ErrorActionPreference = 'Stop'
$resultPath = 'D:\omniroute-monetizer\state\thermal_check_2026_09_06.json'
try {
    $zones = @(Get-CimInstance -Namespace root/wmi -ClassName MSAcpi_ThermalZoneTemperature | ForEach-Object {
        [pscustomobject]@{ Zone=$_.InstanceName; RawKelvinTenths=$_.CurrentTemperature; Celsius=[math]::Round(($_.CurrentTemperature / 10.0)-273.15,1) }
    })
    $result = [pscustomobject]@{Status='ReadCompleted'; Time=(Get-Date).ToString('o'); Zones=$zones; Note='ACPI thermal zones are not necessarily CPU core temperatures.'}
} catch {
    $result = [pscustomobject]@{Status='Unavailable'; Time=(Get-Date).ToString('o'); Error=$_.Exception.Message}
}
$result | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $resultPath -Encoding UTF8
