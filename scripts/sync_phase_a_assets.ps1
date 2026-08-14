$ErrorActionPreference = "Stop"

$PhaseA = "D:\omniroute-phase-a"
$Monetizer = "D:\omniroute-monetizer"

Write-Host "=== SYNC PHASE-A AUTOMATION + EVIDENCE ===" -ForegroundColor Cyan
Write-Host "Phase-A   : $PhaseA"
Write-Host "Monetizer : $Monetizer"
Write-Host ""

if (-not (Test-Path -LiteralPath $PhaseA)) {
    throw "Phase-A directory not found: $PhaseA"
}
if (-not (Test-Path -LiteralPath $Monetizer)) {
    throw "Monetizer directory not found: $Monetizer"
}

$copySets = @(
    @{ From = "automation"; To = "evidence\automation" },
    @{ From = "registry";   To = "evidence\registry" },
    @{ From = "results";    To = "evidence\results" }
)

foreach ($set in $copySets) {
    $src = Join-Path $PhaseA $set.From
    $dst = Join-Path $Monetizer $set.To

    if (-not (Test-Path -LiteralPath $src)) {
        Write-Host "[SKIP] $src not found" -ForegroundColor Yellow
        continue
    }

    New-Item -ItemType Directory -Path $dst -Force | Out-Null

    Get-ChildItem -LiteralPath $src -Force |
        Copy-Item -Destination $dst -Recurse -Force

    Write-Host "[COPIED] $($set.From) -> $($set.To)" -ForegroundColor Green
}

# Copy the Phase-A AGENTS / handoff docs as evidence only.
foreach ($file in @("AGENTS.md", "CODEX_HANDOFF.md")) {
    $src = Join-Path $PhaseA $file
    if (Test-Path -LiteralPath $src) {
        Copy-Item -LiteralPath $src -Destination (Join-Path $Monetizer "evidence\$file") -Force
        Write-Host "[COPIED] evidence\$file" -ForegroundColor Green
    }
}

Write-Host ""
Write-Host "Phase-A automation/evidence synchronized." -ForegroundColor Green
Write-Host "OmniRoute service was NOT touched." -ForegroundColor Green
