# Verify configurations
$validModels = @(
    "moonshotai/kimi-k3-free",
    "nvidia/nemotron-3-ultra-550b-a55b",
    "openai/gpt-oss-20b"
)

Write-Host "=== VS Code TokenRouter Endpoint ==="
$vscode = Get-Content "$env:APPDATA\Code\User\settings.json" | ConvertFrom-Json
$endpoint = $vscode."github.copilot.chat.customEndpoints" | Where-Object { $_.name -eq "Kimi K3 (TokenRouter)" }
$endpoint.models | Select-Object id, name | Format-Table -AutoSize

$invalid = @($endpoint.models | Where-Object { $_.id -notin $validModels })
if ($invalid.Count -gt 0) {
    throw "Invalid model IDs detected in Copilot custom endpoint: $($invalid.id -join ', ')"
}

Write-Host "`n=== Zed TokenRouter Models ==="
$zed = Get-Content "$env:APPDATA\Zed\settings.json" | ConvertFrom-Json
$zed.language_models.openai_compatible.TokenRouter.available_models | Select-Object name, display_name | Format-Table -AutoSize

$invalidZed = @($zed.language_models.openai_compatible.TokenRouter.available_models | Where-Object { $_.name -notin $validModels })
if ($invalidZed.Count -gt 0) {
    throw "Invalid model IDs detected in Zed TokenRouter config: $($invalidZed.name -join ', ')"
}

Write-Host "`n=== Windows Credential Manager ==="
cmdkey /list | Select-String tokenrouter