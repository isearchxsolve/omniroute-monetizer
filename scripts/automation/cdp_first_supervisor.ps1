# cdp_first_supervisor.ps1 - ONE owner of the CDP graduation lane. (rev 2026-10-13)
$chrome = 'C:\Program Files\Google\Chrome\Application\chrome.exe'
$cargs = @('--user-data-dir=D:\anonym\cdp-profile',
          '--profile-directory=Profile 17',
          '--remote-debugging-port=9222', '--no-first-run',
          '--no-default-browser-check', '--hide-crash-restore-bubble',
          '--disable-session-crashed-bubble', '--window-size=1400,900')
$gate = 'd:\anonym\war-log\target-gate-20261012-192723.jsonl'
$profRoot = 'D:\anonym\cdp-profile'

function Test-Cdp {
  try { (Invoke-WebRequest -Uri 'http://127.0.0.1:9222/json/version' -UseBasicParsing -TimeoutSec 6).StatusCode -eq 200 } catch { $false }
}

function Show-Proxies {
  $names = @('HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy', 'ALL_PROXY', 'all_proxy')
  foreach ($n in $names) {
    $v = [Environment]::GetEnvironmentVariable($n)
    if ($v) { Write-Host ('proxy-env ' + $n + ' = ' + $v) }
  }
}

function Kill-Stale {
  $plist = Get-CimInstance Win32_Process -Filter 'Name="python.exe" or Name="pythonw.exe"'
  foreach ($p in $plist) {
    $cl = $p.CommandLine
    if ($cl -and ($cl.IndexOf('cdp_first_graduation') -ge 0)) {
      Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
      Write-Host ('killed pass pid ' + $p.ProcessId)
    }
  }
  $clist = Get-CimInstance Win32_Process -Filter 'Name="chrome.exe"'
  foreach ($p in $clist) {
    $cl = $p.CommandLine
    if ($cl -and ($cl.IndexOf('cdp-profile') -ge 0)) {
      Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
    }
  }
  for ($i = 1; $i -le 15; $i = $i + 1) {
    $left = 0
    $clist2 = Get-CimInstance Win32_Process -Filter 'Name="chrome.exe"'
    foreach ($p in $clist2) {
      $cl = $p.CommandLine
      if ($cl -and ($cl.IndexOf('cdp-profile') -ge 0)) { $left = $left + 1 }
    }
    if ($left -eq 0) { break }
    Start-Sleep -Seconds 1
  }
  Start-Sleep -Seconds 3
}

function Clear-Sessions {
  foreach ($sub in @('Profile 17', 'Default')) {
    $sdir = $profRoot + '\' + $sub + '\Sessions'
    if (Test-Path $sdir) {
      Remove-Item $sdir -Recurse -Force -ErrorAction SilentlyContinue
      Write-Host ('cleared ' + $sdir)
    }
  }
}

while ($true) {
  Write-Host ('=== SUPERVISOR CYCLE ' + (Get-Date -Format o) + ' ===')
  Show-Proxies
  Kill-Stale
  Clear-Sessions
  $owner = 0
  $conn = Get-NetTCPConnection -LocalPort 9222 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
  if ($conn) { $owner = $conn.OwningProcess }
  if ($owner -ne 0) {
    $ocl = ''
    try { $ocl = (Get-CimInstance Win32_Process -Filter ('ProcessId=' + $owner)).CommandLine } catch { $ocl = '' }
    if ($ocl -and ($ocl.IndexOf('cdp-profile') -ge 0)) {
      Write-Host 'port still held by dying cdp chrome - waiting 15s'
      Start-Sleep -Seconds 15
    } else {
      Write-Host ('port 9222 squatted by pid ' + $owner + ' - skipping cycle')
      Start-Sleep -Seconds 30
      continue
    }
  }
  $proc = Start-Process $chrome -ArgumentList $cargs -PassThru
  Write-Host ('launched chrome pid ' + $proc.Id)
  $up = $false
  for ($i = 1; $i -le 10; $i = $i + 1) {
    Start-Sleep -Seconds 3
    if (Test-Cdp) {
      $o2 = 0
      $c2 = Get-NetTCPConnection -LocalPort 9222 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
      if ($c2) { $o2 = $c2.OwningProcess }
      $oc2 = ''
      try { $oc2 = (Get-CimInstance Win32_Process -Filter ('ProcessId=' + $o2)).CommandLine } catch { $oc2 = '' }
      if ($o2 -eq $proc.Id) { $up = $true; break }
      if ($oc2 -and ($oc2.IndexOf('cdp-profile') -ge 0)) {
        $up = $true
        Write-Host ('port owner pid ' + $o2 + ' is our tree - accepting')
        break
      }
      Write-Host ('port answer from pid ' + $o2 + ' - phantom, keep waiting')
    }
  }
  if (-not $up) { Write-Host 'chrome would not start - wait 30s and retry'; Start-Sleep -Seconds 30; continue }
  if ($proc.HasExited) {
    Write-Host 'launched chrome exited (handoff to zombie) - kill and retry'
    Kill-Stale
    Start-Sleep -Seconds 15
    continue
  }
  Write-Host 'chrome verified up'
  python -u D:\omniroute-monetizer\scripts\automation\cdp_first_graduation.py --gate $gate
  Write-Host 'pass exited - supervising next cycle'
  Start-Sleep -Seconds 10
}
