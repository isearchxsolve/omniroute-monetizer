$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path

# Prefer the persistent Python created by the v10 diagnostic. Fall back to the
# older portable path only if it exists. Never use system Python implicitly.
$PyCandidates = @(
    (Join-Path $Root 'tools\python311\python.exe'),
    (Join-Path $Root 'tools\py311\python.exe')
)
$PyExe = $PyCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
$ScriptCandidates = @(
    (Join-Path $Root 'omniroute_provider_recovery_v11_smoketested.py'),
    (Join-Path $Root 'omniroute_provider_recovery_v11.py')
)
$Script = $ScriptCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
$DiagDir = Join-Path $Root 'omniroute_provider_recovery'

$env:PYTHONUNBUFFERED = '1'
$env:OMNIROUTE_RECOVERY_DIR = $DiagDir

Write-Host '============================================================' -ForegroundColor Cyan
Write-Host ' OmniRoute Provider Recovery v11 - SMOKE-TESTED' -ForegroundColor Cyan
Write-Host ' API refresh + exact UI re-auth + API verification' -ForegroundColor Cyan
Write-Host '============================================================' -ForegroundColor Cyan

if (-not $PyExe) {
    throw "No supported Python runtime found. Expected one of:`n  $($PyCandidates -join "`n  ")`nRun the v10 environment setup first; this runner will not mutate/install Python."
}

if (-not $Script) {
    throw "Recovery script not found. Expected one of:`n  $($ScriptCandidates -join "`n  ")"
}

Write-Host "[+] Python: $PyExe" -ForegroundColor Green
Write-Host "[+] Script: $Script" -ForegroundColor Green

# Smoke-test imports before touching OmniRoute.
$test = & $PyExe -c "import sys, playwright, requests; print('ENV_OK'); print(sys.version.split()[0])" 2>&1
if ($LASTEXITCODE -ne 0 -or "$test" -notmatch 'ENV_OK') {
    throw "Python environment cannot import Playwright/requests.`n$test"
}
Write-Host '[+] Python / Playwright / requests smoke test: OK' -ForegroundColor Green

# Verify the actual script parses before allowing it to mutate anything.
$compile = & $PyExe -m py_compile $Script 2>&1
if ($LASTEXITCODE -ne 0) {
    throw "Recovery script failed Python syntax compilation.`n$compile"
}
Write-Host '[+] Python syntax compile: OK' -ForegroundColor Green

if (-not $env:OMNIROUTE_PASSWORD) {
    $sec = Read-Host 'OmniRoute dashboard password' -AsSecureString
    $ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($sec)
    try {
        $env:OMNIROUTE_PASSWORD = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr)
    }
    finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr)
    }
}

Write-Host '[+] Starting provider recovery...' -ForegroundColor Yellow
Write-Host '    Final success is determined by OmniRoute API verification, not UI text.' -ForegroundColor DarkGray

& $PyExe $Script
$code = $LASTEXITCODE

if ($code -ne 0) {
    throw "Recovery script exited with code $code. Review the output above and $DiagDir."
}

Write-Host '============================================================' -ForegroundColor Cyan
Write-Host ' Recovery finished successfully.' -ForegroundColor Green
Write-Host " Evidence/results: $DiagDir" -ForegroundColor Cyan
Write-Host '============================================================' -ForegroundColor Cyan
