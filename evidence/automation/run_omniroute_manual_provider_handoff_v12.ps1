$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$PyCandidates = @(
    (Join-Path $Root 'tools\python311\python.exe'),
    (Join-Path $Root 'tools\py311\python.exe')
)
$PyExe = $PyCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
$Script = Join-Path $Root 'omniroute_manual_provider_handoff_v12.py'

Write-Host '============================================================' -ForegroundColor Cyan
Write-Host ' OmniRoute MANUAL PROVIDER HANDOFF v12' -ForegroundColor Cyan
Write-Host ' OPEN PROVIDER -> YOU DO THE REST' -ForegroundColor Cyan
Write-Host '============================================================' -ForegroundColor Cyan

if (-not $PyExe) {
    throw "No supported Python runtime found. Expected:`n  $($PyCandidates -join "`n  ")"
}
if (-not (Test-Path -LiteralPath $Script)) {
    throw "Missing script: $Script"
}

$env:PYTHONUNBUFFERED = '1'

# 1) Import smoke test.
$envTest = & $PyExe -c "import playwright; print('PLAYWRIGHT_OK')" 2>&1
if ($LASTEXITCODE -ne 0 -or "$envTest" -notmatch 'PLAYWRIGHT_OK') {
    throw "Playwright import failed.`n$envTest"
}

# 2) Bytecode/syntax smoke test.
$compile = & $PyExe -m py_compile $Script 2>&1
if ($LASTEXITCODE -ne 0) {
    throw "Python syntax check failed.`n$compile"
}

# 3) Real browser launch smoke test. This catches missing Chromium before the user is involved.
$browserTest = @'
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    b.close()
print("BROWSER_OK")
'@
$browserResult = $browserTest | & $PyExe - 2>&1
if ($LASTEXITCODE -ne 0 -or "$browserResult" -notmatch 'BROWSER_OK') {
    throw "Playwright Chromium launch failed.`n$browserResult"
}

Write-Host '[+] Python + Playwright + syntax + Chromium smoke tests: OK' -ForegroundColor Green

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

Write-Host ''
Write-Host 'Examples: codex | xai-oauth | cline | antigravity | agy | amazon-q | openrouter' -ForegroundColor DarkGray
Write-Host ''

# Pass all user arguments through unchanged. The Python script does all navigation only.
& $PyExe $Script @args
$code = $LASTEXITCODE
if ($code -ne 0) {
    throw "Manual provider handoff exited with code $code"
}
