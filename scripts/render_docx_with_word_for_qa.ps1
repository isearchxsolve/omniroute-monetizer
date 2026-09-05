param(
    [Parameter(Mandatory = $true)][string]$InputDocx,
    [Parameter(Mandatory = $true)][string]$OutputPdf
)

$ErrorActionPreference = 'Stop'
$outputDirectory = Split-Path -Parent $OutputPdf
New-Item -ItemType Directory -Force -Path $outputDirectory | Out-Null

$wordApp = $null
$wordDoc = $null
try {
    $wordApp = New-Object -ComObject Word.Application
    $wordApp.Visible = $false
    $wordApp.DisplayAlerts = 0
    $wordDoc = $wordApp.Documents.Open($InputDocx, $false, $true)
    $wordDoc.Fields.Update() | Out-Null
    $wordDoc.ExportAsFixedFormat($OutputPdf, 17)
    $wordDoc.Close(0)
    $wordDoc = $null
    $wordApp.Quit()
    $wordApp = $null
    Write-Output $OutputPdf
}
finally {
    if ($null -ne $wordDoc) { $wordDoc.Close(0) }
    if ($null -ne $wordApp) { $wordApp.Quit() }
    [GC]::Collect()
    [GC]::WaitForPendingFinalizers()
}
