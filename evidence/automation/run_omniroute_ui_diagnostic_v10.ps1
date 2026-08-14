# run_omniroute_ui_diagnostic_v10.ps1
# Portable Python bootstrap (same proven method as fix_omniroute.ps1).
# Uses the embeddable zip + get-pip.py instead of the full Windows installer.

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Tools = Join-Path $Root 'tools'
$PyDir = Join-Path $Tools 'python311'
$PyExe = Join-Path $PyDir 'python.exe'
$DiagScript = Join-Path $Root 'omniroute_ui_diagnostic_v10.py'
$DiagDir = Join-Path $Root 'omniroute_ui_diagnostic'
$PythonZipUrl = 'https://www.python.org/ftp/python/3.11.9/python-3.11.9-embed-amd64.zip'
$GetPipUrl = 'https://bootstrap.pypa.io/get-pip.py'
$Omni = 'http://localhost:20128'

function Fail([string]$m) {
    Write-Host "`nERROR: $m" -ForegroundColor Red
    exit 1
}

Write-Host '============================================================' -ForegroundColor Cyan
Write-Host ' OmniRoute UI Diagnostic v10 — ONE CLEAN BOOTSTRAP' -ForegroundColor Cyan
Write-Host ' (portable embeddable Python, same as working fix script)' -ForegroundColor Cyan
Write-Host '============================================================' -ForegroundColor Cyan

New-Item -ItemType Directory -Force -Path $Tools | Out-Null

# ── [1] Portable Python (embeddable zip) ──────────────────────────
if (-not (Test-Path $PyExe)) {
    Write-Host '[1/6] Installing private portable Python 3.11...' -ForegroundColor Yellow

    $zipPath = Join-Path $Tools 'python-3.11.9-embed-amd64.zip'
    if (-not (Test-Path $zipPath)) {
        Write-Host '  Downloading embeddable Python zip...' -ForegroundColor DarkGray
        Invoke-WebRequest -Uri $PythonZipUrl -OutFile $zipPath
    }

    if (Test-Path $PyDir) {
        Remove-Item -Recurse -Force $PyDir
    }
    New-Item -ItemType Directory -Force -Path $PyDir | Out-Null

    Write-Host '  Extracting...' -ForegroundColor DarkGray
    Expand-Archive -Path $zipPath -DestinationPath $PyDir -Force

    if (-not (Test-Path $PyExe)) {
        Write-Host "  ERROR: portable python.exe not found at $PyExe after extraction." -ForegroundColor Red
        Write-Host "  Contents of $PyDir :" -ForegroundColor Yellow
        Get-ChildItem $PyDir -ErrorAction SilentlyContinue | ForEach-Object { Write-Host "    $($_.Name)" }
        Fail "Python extraction failed: $PyExe"
    }
    Write-Host "  Portable Python confirmed at $PyExe" -ForegroundColor DarkGray

    # Embeddable builds ship a ._pth that disables site-packages.
    # Enable "import site" so pip-installed packages are importable.
    $pthFile = Get-ChildItem $PyDir -Filter 'python*._pth' -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $pthFile) {
        Write-Host '  WARNING: could not find a ._pth file under python311' -ForegroundColor Yellow
    } else {
        $pthContent = Get-Content $pthFile.FullName
        $newContent = @()
        $foundImportSite = $false
        foreach ($line in $pthContent) {
            if ($line -match 'import\s+site') {
                $newContent += 'import site'
                $foundImportSite = $true
            } else {
                $newContent += $line
            }
        }
        if (-not $foundImportSite) { $newContent += 'import site' }
        Set-Content -Path $pthFile.FullName -Value $newContent
        Write-Host "  Patched $($pthFile.Name) to enable site-packages" -ForegroundColor DarkGray
    }
} else {
    Write-Host '[1/6] Private portable Python already present.' -ForegroundColor Green
}

if (-not (Test-Path $PyExe)) {
    Fail "Python installation failed: $PyExe"
}

# ── [2] Bootstrap pip ─────────────────────────────────────────────
Write-Host '[2/6] Bootstrapping / verifying pip...' -ForegroundColor Yellow
$pipOk = $false
try {
    $null = & $PyExe -m pip --version 2>$null
    if ($LASTEXITCODE -eq 0) { $pipOk = $true }
} catch { }

if (-not $pipOk) {
    $getPip = Join-Path $Tools 'get-pip.py'
    if (-not (Test-Path $getPip)) {
        Write-Host '  Downloading get-pip.py...' -ForegroundColor DarkGray
        Invoke-WebRequest -Uri $GetPipUrl -OutFile $getPip
    }
    & $PyExe $getPip --no-warn-script-location
    if ($LASTEXITCODE -ne 0) {
        Fail 'pip bootstrap (get-pip.py) failed.'
    }
}

& $PyExe -m pip --version
if ($LASTEXITCODE -ne 0) {
    Fail 'pip is still unavailable after bootstrap.'
}

# ── [3] Install diagnostic dependencies ───────────────────────────
Write-Host '[3/6] Installing exact diagnostic dependencies...' -ForegroundColor Yellow
& $PyExe -m pip install --upgrade --disable-pip-version-check --no-warn-script-location requests playwright
if ($LASTEXITCODE -ne 0) {
    Fail 'pip install failed.'
}

$verify = & $PyExe -c "import requests, playwright; print('OK')" 2>&1
if ("$verify" -notmatch 'OK') {
    Write-Host "  ERROR: requests/playwright still not importable. Output:" -ForegroundColor Red
    Write-Host "  $verify" -ForegroundColor Red
    Fail 'Environment verification failed after pip install.'
}
Write-Host '  Environment OK (requests + playwright importable)' -ForegroundColor Green

# ── [4] Chromium for Playwright ───────────────────────────────────
Write-Host '[4/6] Ensuring Chromium...' -ForegroundColor Yellow
$env:PLAYWRIGHT_BROWSERS_PATH = Join-Path $Tools 'playwright-browsers'
& $PyExe -m playwright install chromium
if ($LASTEXITCODE -ne 0) {
    Fail 'Chromium installation failed.'
}

# ── [5] OmniRoute reachability ────────────────────────────────────
Write-Host '[5/6] Checking OmniRoute...' -ForegroundColor Yellow
try {
    $r = Invoke-WebRequest -UseBasicParsing -Uri $Omni -TimeoutSec 5
    Write-Host "  OmniRoute HTTP $($r.StatusCode)" -ForegroundColor Green
} catch {
    Fail "OmniRoute is not responding at $Omni"
}

if (-not $env:OMNIROUTE_PASSWORD) {
    $sec = Read-Host 'OmniRoute dashboard password' -AsSecureString
    $ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($sec)
    try {
        $env:OMNIROUTE_PASSWORD = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr)
    } finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr)
    }
}

# ── [6] Run diagnostic ────────────────────────────────────────────
Write-Host '[6/6] Running non-destructive UI/API diagnostic...' -ForegroundColor Cyan
$env:OMNIROUTE_DIAG_DIR = $DiagDir

if (-not (Test-Path $PyExe)) {
    Fail "python.exe disappeared before run step: $PyExe"
}
if (-not (Test-Path $DiagScript)) {
    Fail "Diagnostic script not found: $DiagScript"
}

& $PyExe $DiagScript
if ($LASTEXITCODE -ne 0) {
    Fail 'Diagnostic failed.'
}

Write-Host "`nBundle created: $DiagDir" -ForegroundColor Green
Write-Host 'Upload the ENTIRE folder. No provider configuration was changed.' -ForegroundColor Yellow
