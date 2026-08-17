# auto_checkpoint_watchdog.ps1
# Git-saves all fleet projects every $IntervalSeconds so a power cut can never
# lose more than one interval of agent work. Runs until the window is closed.
#
# Usage (already launched in its own console):
#   powershell -ExecutionPolicy Bypass -File d:\omniroute-monetizer\scratch\auto_checkpoint_watchdog.ps1

$ErrorActionPreference = "SilentlyContinue"

# Per-project checkpoint intervals (seconds). Small repos get 60 s; the huge
# ases repo (node_modules tracked) gets 300 s to avoid I/O contention with its
# running Selenium tests. index.lock detection prevents fighting agents' own
# git commands.
$Projects = [ordered]@{
    'd:\omniroute-monetizer'   = 60
    'd:\neon_unified'          = 60
    'C:\god_ai\crypto-trader-v1_1' = 120
    'C:\god_ai\ases_v3_1'      = 300
}

$TickSeconds = 60           # base polling tick
$LogFile = 'd:\omniroute-monetizer\state\auto_checkpoint.log'

function Write-Log([string]$msg) {
    $line = "[" + (Get-Date -Format 'yyyy-MM-dd HH:mm:ss') + "] " + $msg
    Write-Host $line
    Add-Content -Path $LogFile -Value $line -Encoding UTF8
}

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  AUTO-CHECKPOINT WATCHDOG" -ForegroundColor Cyan
Write-Host "  Tick: every $TickSeconds s; per-project intervals:" -ForegroundColor Cyan
foreach ($k in $Projects.Keys) {
    Write-Host ("    " + (Split-Path $k -Leaf).PadRight(22) + " every " + $Projects[$k] + " s") -ForegroundColor DarkCyan
}
Write-Host "  Log: $LogFile" -ForegroundColor Cyan
Write-Host "  Close this window to stop. Fleet work is unaffected." -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Log "WATCHDOG STARTED (tick=$TickSeconds s; intervals: $(($Projects.Keys | ForEach-Object { (Split-Path $_ -Leaf) + '=' + $Projects[$_] + 's' }) -join ', '))"

$lastRun = @{}
$cycle = 0
while ($true) {
    $cycle++
    $now = Get-Date
    foreach ($proj in $Projects.Keys) {
        $interval = $Projects[$proj]
        $name = Split-Path $proj -Leaf
        # Not yet due for this project.
        if ($lastRun.ContainsKey($proj) -and (($now - $lastRun[$proj]).TotalSeconds -lt $interval)) {
            continue
        }
        if (-not (Test-Path (Join-Path $proj '.git'))) {
            Write-Log "$name : SKIP (no .git)"
            $lastRun[$proj] = $now
            continue
        }
        # Never fight an agent's in-flight git operation over the index lock.
        if (Test-Path (Join-Path $proj '.git\index.lock')) {
            Write-Log "$name : SKIP (git busy - index.lock present; retry next tick)"
            continue
        }
        $lastRun[$proj] = $now
        Push-Location $proj
        # Only commit when there is something to save.
        $dirty = git status --porcelain 2>$null
        if ([string]::IsNullOrWhiteSpace($dirty)) {
            if ($cycle % 10 -eq 1) { Write-Log "$name : clean (nothing to save)" }
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
    Start-Sleep -Seconds $TickSeconds
}
