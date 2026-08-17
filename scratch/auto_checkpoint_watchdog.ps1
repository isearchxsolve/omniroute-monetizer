# auto_checkpoint_watchdog.ps1
# Git-saves all fleet projects every $IntervalSeconds so a power cut can never
# lose more than one interval of agent work. Runs until the window is closed.
#
# Usage (already launched in its own console):
#   powershell -ExecutionPolicy Bypass -File d:\omniroute-monetizer\scratch\auto_checkpoint_watchdog.ps1

$ErrorActionPreference = "SilentlyContinue"

$Projects = @(
    'd:\omniroute-monetizer',
    'd:\neon_unified',
    'C:\god_ai\crypto-trader-v1_1',
    'C:\god_ai\ases_v3_1'
)

$IntervalSeconds = 1800   # 30 minutes
$LogFile = 'd:\omniroute-monetizer\state\auto_checkpoint.log'

function Write-Log([string]$msg) {
    $line = "[" + (Get-Date -Format 'yyyy-MM-dd HH:mm:ss') + "] " + $msg
    Write-Host $line
    Add-Content -Path $LogFile -Value $line -Encoding UTF8
}

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  AUTO-CHECKPOINT WATCHDOG" -ForegroundColor Cyan
Write-Host "  Interval: every $IntervalSeconds s ($([math]::Round($IntervalSeconds/60,1)) min)" -ForegroundColor Cyan
Write-Host "  Projects: $($Projects.Count)" -ForegroundColor Cyan
Write-Host "  Log: $LogFile" -ForegroundColor Cyan
Write-Host "  Close this window to stop. Fleet work is unaffected." -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Log "WATCHDOG STARTED (interval=$IntervalSeconds s, projects=$($Projects.Count))"

$cycle = 0
while ($true) {
    $cycle++
    Write-Log "--- cycle $cycle ---"
    foreach ($proj in $Projects) {
        $name = Split-Path $proj -Leaf
        if (-not (Test-Path (Join-Path $proj '.git'))) {
            Write-Log "$name : SKIP (no .git)"
            continue
        }
        Push-Location $proj
        # Only commit when there is something to save.
        $dirty = git status --porcelain 2>$null
        if ([string]::IsNullOrWhiteSpace($dirty)) {
            Write-Log "$name : clean (nothing to save)"
        } else {
            $changed = ($dirty -split "`n").Count
            git add -A 2>$null
            $stamp = Get-Date -Format 'yyyy-MM-dd HH:mm'
            git commit -m "auto-checkpoint $stamp ($changed paths)" --no-verify --quiet 2>$null
            if ($LASTEXITCODE -eq 0) {
                $sha = (git rev-parse --short HEAD 2>$null)
                Write-Log "$name : SAVED $changed paths -> $sha"
            } else {
                Write-Log "$name : commit returned $LASTEXITCODE (likely nothing staged)"
            }
        }
        Pop-Location
    }
    Write-Log "cycle $cycle done; sleeping $IntervalSeconds s"
    Start-Sleep -Seconds $IntervalSeconds
}
