# KIMI K3 FREE & VS CODE / ZED SETUP GUIDE
**Complete Configuration Reference & Dual-Gateway Architecture**

---

## 1. Overview
This setup enables **Kimi K3 (Moonshot AI)** completely free as an AI coding model across **VS Code** (GitHub Copilot / Custom Language Model Endpoints) and **Zed Editor**, featuring a **Dual-Gateway Architecture**:
1. **Remote Gateway:** Direct TokenRouter endpoint (`https://api.tokenrouter.com/v1`) using free API tokens.
2. **Local Gateway:** Local OmniRoute cluster (`http://localhost:20128/v1`) providing low-latency cascading (`kimi-coding`, `auto/best-coding`, `frontier`) with zero client-side latency timeouts.

---

## 2. VS Code Configuration (`%APPDATA%\Code\User\settings.json`)

Add the custom endpoint definitions under `github.copilot.chat.customEndpoints`:

```json
{
    "github.copilot.chat.customEndpoints": [
        {
            "name": "Kimi K3 (TokenRouter)",
            "vendor": "customendpoint",
            "apiKey": "${input:chat.lm.secret.tokenrouter}",
            "apiType": "chat-completions",
            "models": [
                {
                    "id": "moonshotai/kimi-k3-free",
                    "name": "Kimi K3 Free",
                    "url": "https://api.tokenrouter.com/v1/chat/completions",
                    "toolCalling": true,
                    "vision": false,
                    "maxInputTokens": 128000,
                    "maxOutputTokens": 16000
                }
            ]
        },
        {
            "name": "OmniRoute (Kimi K3 & Frontier)",
            "vendor": "customendpoint",
            "apiKey": "sk-2daf4dd6d1e45047-d60156-541a3aeb",
            "apiType": "chat-completions",
            "models": [
                {
                    "id": "kimi-coding",
                    "name": "Kimi Coding (OmniRoute)",
                    "url": "http://localhost:20128/v1/chat/completions",
                    "toolCalling": true,
                    "vision": false,
                    "maxInputTokens": 128000,
                    "maxOutputTokens": 16000
                },
                {
                    "id": "auto/best-coding",
                    "name": "Best Coding (OmniRoute)",
                    "url": "http://localhost:20128/v1/chat/completions",
                    "toolCalling": true,
                    "vision": false,
                    "maxInputTokens": 128000,
                    "maxOutputTokens": 16000
                },
                {
                    "id": "frontier",
                    "name": "Frontier (OmniRoute)",
                    "url": "http://localhost:20128/v1/chat/completions",
                    "toolCalling": true,
                    "vision": false,
                    "maxInputTokens": 128000,
                    "maxOutputTokens": 16000
                }
            ]
        }
    ]
}
```

---

## 3. Zed Editor Configuration (`%APPDATA%\Zed\settings.json`)

Configure OmniRoute with `kimi-coding` in Zed's available models:

```json
{
    "language_models": {
        "openai_compatible": {
            "OmniRoute": {
                "api_url": "http://localhost:20128/v1",
                "available_models": [
                    {
                        "name": "kimi-coding",
                        "display_name": "⭐ Kimi K3 / Kimi Coding",
                        "max_tokens": 128000
                    },
                    {
                        "name": "auto/best-coding",
                        "display_name": "⭐ OmniRoute Best Coding",
                        "max_tokens": 128000
                    },
                    {
                        "name": "frontier",
                        "display_name": "⭐ OmniRoute Frontier Max",
                        "max_tokens": 128000
                    }
                ]
            }
        }
    }
}
```

---

## 4. Operational Usage

### Using in VS Code:
1. Open the **GitHub Copilot Chat** / AI Assistant panel.
2. Click the model dropdown picker.
3. Select **`Kimi K3 Free`** (TokenRouter) or **`OmniRoute (Kimi K3 & Frontier)`**.
4. If using TokenRouter, paste your free key from [https://www.tokenrouter.com/](https://www.tokenrouter.com/) when prompted.

### Using in Zed Editor:
1. Open the assistant panel (`Ctrl+?` or `Cmd+?`).
2. Select **`⭐ Kimi K3 / Kimi Coding`** or **`⭐ OmniRoute Best Coding`**.
3. Prompts route directly through the low-latency OmniRoute gateway.
