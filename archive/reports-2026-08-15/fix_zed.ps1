# Fix Zed settings - add qwen model
$zedPath = "$env:APPDATA\Zed\settings.json"
$zed = Get-Content $zedPath | ConvertFrom-Json

$tokenRouterModels = $zed.language_models.openai_compatible.TokenRouter.available_models
$hasQwen = $tokenRouterModels | Where-Object { $_.name -eq "qwen/qwen3.8-max-free" }
if (-not $hasQwen) {
    $tokenRouterModels += @{
        name = "qwen/qwen3.8-max-free"
        display_name = "Qwen 3.8 Max Free (TokenRouter)"
        max_tokens = 128000
    }
    $zed | ConvertTo-Json -Depth 10 | Set-Content $zedPath -Encoding UTF8
    Write-Host "Zed settings updated with qwen model"
} else {
    Write-Host "Qwen model already exists in Zed"
}

# Verify Windows Credential Manager password was updated
Write-Host "`n=== Verifying Credential Manager ==="
$cred = cmdkey /list | Select-String "zed:url=https://api.tokenrouter.com/v1"
if ($cred) {
    Write-Host "Target found: $cred"
    Write-Host "Note: cmdkey /list does not show passwords for security"
}