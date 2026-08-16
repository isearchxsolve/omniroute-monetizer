# Update VS Code, Zed, and Windows Credential Manager with a validated TokenRouter key
# Keep credentials in environment variables instead of hardcoding them.
$apiKey = $env:TOKENROUTER_API_KEY
if (-not $apiKey) {
    throw "TOKENROUTER_API_KEY is not set. Export it before running this script."
}

# 1. Update VS Code settings.json
$vscodePath = "$env:APPDATA\Code\User\settings.json"
$vscode = Get-Content $vscodePath | ConvertFrom-Json

foreach ($endpoint in $vscode."github.copilot.chat.customEndpoints") {
    if ($endpoint.name -eq "Kimi K3 (TokenRouter)") {
        $endpoint.apiKey = $apiKey

        $validModels = @(
            "moonshotai/kimi-k3-free",
            "nvidia/nemotron-3-ultra-550b-a55b",
            "openai/gpt-oss-20b"
        )

        $endpoint.models = @(
            [pscustomobject]@{
                id = "moonshotai/kimi-k3-free"
                name = "Kimi K3 Free"
                url = "https://api.tokenrouter.com/v1/chat/completions"
                toolCalling = $true
                vision = $false
                maxInputTokens = 128000
                maxOutputTokens = 16000
            },
            [pscustomobject]@{
                id = "nvidia/nemotron-3-ultra-550b-a55b"
                name = "Nemotron 3 Ultra 550B"
                url = "https://api.tokenrouter.com/v1/chat/completions"
                toolCalling = $true
                vision = $false
                maxInputTokens = 128000
                maxOutputTokens = 16000
            },
            [pscustomobject]@{
                id = "openai/gpt-oss-20b"
                name = "GPT-OSS 20B"
                url = "https://api.tokenrouter.com/v1/chat/completions"
                toolCalling = $true
                vision = $false
                maxInputTokens = 128000
                maxOutputTokens = 16000
            }
        )
    }
}

$vscode | ConvertTo-Json -Depth 10 | Set-Content $vscodePath -Encoding UTF8
Write-Host "✅ VS Code settings updated"

# 2. Update Zed settings.json - add known-good TokenRouter models only
$zedPath = "$env:APPDATA\Zed\settings.json"
$zed = Get-Content $zedPath | ConvertFrom-Json

$tokenRouterModels = @(
    [pscustomobject]@{
        name = "moonshotai/kimi-k3-free"
        display_name = "Kimi K3 Free (TokenRouter)"
        max_tokens = 128000
    },
    [pscustomobject]@{
        name = "nvidia/nemotron-3-ultra-550b-a55b"
        display_name = "Nemotron 3 Ultra 550B (TokenRouter)"
        max_tokens = 128000
    },
    [pscustomobject]@{
        name = "openai/gpt-oss-20b"
        display_name = "GPT-OSS 20B (TokenRouter)"
        max_tokens = 128000
    }
)

$zed.language_models.openai_compatible.TokenRouter.available_models = $tokenRouterModels
$zed | ConvertTo-Json -Depth 10 | Set-Content $zedPath -Encoding UTF8
Write-Host "✅ Zed settings updated"

# 3. Update Windows Credential Manager
cmdkey /generic:"zed:url=https://api.tokenrouter.com/v1" /user:"Bearer" /pass:"$apiKey"
Write-Host "✅ Windows Credential Manager updated"

Write-Host "🎉 ALL CONFIGURATIONS UPDATED SUCCESSFULLY"
Write-Host "Restart VS Code and Zed to apply changes"