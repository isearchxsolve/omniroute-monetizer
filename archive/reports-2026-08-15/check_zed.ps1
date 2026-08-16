$zed = Get-Content "$env:APPDATA\Zed\settings.json" | ConvertFrom-Json
$models = $zed.language_models.openai_compatible.TokenRouter.available_models
$models | ForEach-Object { Write-Host "$($_.name) -> $($_.display_name)" }