$ErrorActionPreference = "Stop"
$target = "D:\omniroute-monetizer"
$phaseA = "D:\omniroute-phase-a"

Write-Host "=== OmniRoute Monetizer workspace setup ===" -ForegroundColor Cyan

New-Item -ItemType Directory -Path $target -Force | Out-Null
foreach ($d in @("docs","prompts","scripts","evidence","state","logs")) {
    New-Item -ItemType Directory -Path (Join-Path $target $d) -Force | Out-Null
}

foreach ($d in @("automation","registry","results","docs")) {
    $src = Join-Path $phaseA $d
    $dst = Join-Path $target "evidence\$d"
    if (Test-Path $src) {
        New-Item -ItemType Directory -Path $dst -Force | Out-Null
        Copy-Item "$src\*" $dst -Recurse -Force
    }
}

Copy-Item "$phaseA\AGENTS.md" "$target\evidence\AGENTS_PHASE_A.md" -Force
if (Test-Path "$phaseA\CODEX_HANDOFF.md") {
    Copy-Item "$phaseA\CODEX_HANDOFF.md" "$target\evidence\CODEX_HANDOFF.md" -Force
}

New-Item -ItemType Directory -Path "$target\scripts\source" -Force | Out-Null

Write-Host ""
Write-Host "Created: $target" -ForegroundColor Green
Write-Host "Copied Phase-A evidence." -ForegroundColor Green
Write-Host ""
Write-Host "Place the current master script here:" -ForegroundColor Yellow
Write-Host "$target\scripts\source\omniroute_full_setup.py"
Write-Host ""
Write-Host "Then give the agent: $target\prompts\INITIAL_PROMPT.txt" -ForegroundColor Cyan
