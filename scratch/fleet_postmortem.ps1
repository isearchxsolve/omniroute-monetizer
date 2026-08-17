$projects = [ordered]@{
  'nvidia-1' = 'd:\ideation_to_prototype'
  'nvidia-2' = 'd:\emergentsh_latest'
  'alibaba' = 'd:\neon_unified'
  'tokenrouter-1' = 'C:\god_ai\oioi\oioi'
  'tokenrouter-2' = 'C:\god_ai\crypto-trader-v1_1'
  'tokenrouter-3' = 'C:\god_ai\ases_v3_1'
}
foreach ($slot in $projects.Keys) {
  $dir = $projects[$slot]
  Write-Output "===== $slot ($dir) ====="
  Write-Output "--- last commits ---"
  git -C $dir log --oneline -6 2>&1 | Out-String
  Write-Output "--- FLEET_WORKLOG.md ---"
  if (Test-Path (Join-Path $dir 'FLEET_WORKLOG.md')) { Write-Output "EXISTS" } else { Write-Output "missing" }
  Write-Output "--- dirty files (first 8) ---"
  git -C $dir status --porcelain 2>&1 | Select-Object -First 8 | Out-String
}
Write-Output "===== junk file check in ideation_to_prototype ====="
Get-ChildItem 'd:\ideation_to_prototype' -File | Where-Object { $_.Name -match 'Let me|worklog entry' } | Select-Object Name, Length | Format-Table -AutoSize | Out-String
