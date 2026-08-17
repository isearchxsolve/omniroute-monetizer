# Kill Playwright-launched Chrome instances by their MAIN process (tree kill),
# so all renderer/GPU/utility children die with the parent.
# Playwright main processes have scoped_dir user-data-dir and NO --type= flag.

$mains = Get-CimInstance Win32_Process -Filter "Name='chrome.exe'" |
    Where-Object {
        ($_.CommandLine -like '*scoped_dir*') -and
        ($_.CommandLine -notlike '*--type=*')
    }

Write-Output ("Playwright MAIN procs (no --type=): " + (@($mains)).Count)
foreach ($m in $mains) {
    Write-Output ("  tree-kill PID " + $m.ProcessId)
    Start-Process -FilePath "taskkill.exe" -ArgumentList ("/F /T /PID " + $m.ProcessId) -Wait -NoNewWindow -ErrorAction SilentlyContinue | Out-Null
}

Start-Sleep -Seconds 3

# Sweep any remaining scoped_dir stragglers individually
$stragglers = Get-CimInstance Win32_Process -Filter "Name='chrome.exe'" |
    Where-Object { $_.CommandLine -like '*scoped_dir*' }
$spids = @($stragglers | ForEach-Object ProcessId)
Write-Output ("Stragglers after tree-kill: " + $spids.Count)
foreach ($p in $spids) {
    Start-Process -FilePath "taskkill.exe" -ArgumentList ("/F /PID " + $p) -Wait -NoNewWindow -ErrorAction SilentlyContinue | Out-Null
}

Start-Sleep -Seconds 2
$final = @(Get-CimInstance Win32_Process -Filter "Name='chrome.exe'" | Where-Object { $_.CommandLine -like '*scoped_dir*' })
Write-Output ("FINAL scoped_dir procs: " + $final.Count)
Write-Output ("FINAL total chrome procs: " + @(Get-Process chrome -ErrorAction SilentlyContinue).Count)
