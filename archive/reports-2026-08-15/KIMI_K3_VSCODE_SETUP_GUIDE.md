# KIMI K3 FREE & VS CODE / ZED SETUP GUIDE
**Complete Configuration Reference, Dual-Gateway Architecture & Autonomous Credential Injection**

---

## 1. Architecture Overview
This setup enables **Kimi K3 (Moonshot AI)** completely free as an AI coding model across **VS Code** (GitHub Copilot / Custom Language Model Endpoints) and **Zed Editor**, featuring a **Dual-Gateway Architecture**:

1. **Remote Gateway:** Direct TokenRouter endpoint (`https://api.tokenrouter.com/v1`) using free API tokens.
2. **Local Gateway:** Local OmniRoute cluster (`http://localhost:20128/v1`) providing low-latency cascading (`kimi-coding`, `moonshotai/kimi-k3-free`, `auto/best-coding`, `frontier`) with full function calling / tool calling support.

```
+-----------------------------------------------------------+
|                        Client Layer                       |
|           VS Code / Zed Editor / Codex CLI                |
+-----------------------------+-----------------------------+
                              |
               +--------------+--------------+
               |                             |
               v                             v
+-------------------------------+ +-------------------------+
|     Local OmniRoute Gate      | |   Remote TokenRouter    |
|   (http://localhost:20128/v1) | |  (api.tokenrouter.com)  |
|                               | |                         |
| - kimi-coding                 | | - moonshotai/kimi-k3-   |
| - moonshotai/kimi-k3-free     | |   free                  |
| - auto/best-coding            | |                         |
| - frontier / fusion-coder     | |                         |
+-------------------------------+ +-------------------------+
```

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
            "apiKey": "<REDACTED>",
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
                    "id": "moonshotai/kimi-k3-free",
                    "name": "Kimi K3 Free (OmniRoute)",
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

Configure both `TokenRouter` and `OmniRoute` in Zed's available models:

```json
{
    "language_models": {
        "openai_compatible": {
            "TokenRouter": {
                "api_url": "https://api.tokenrouter.com/v1",
                "available_models": [
                    {
                        "name": "moonshotai/kimi-k3-free",
                        "display_name": "⭐ Kimi K3 Free (TokenRouter)",
                        "max_tokens": 128000
                    }
                ]
            },
            "OmniRoute": {
                "api_url": "http://localhost:20128/v1",
                "available_models": [
                    {
                        "name": "kimi-coding",
                        "display_name": "⭐ Kimi K3 / Kimi Coding (Exclusive)",
                        "max_tokens": 128000
                    },
                    {
                        "name": "moonshotai/kimi-k3-free",
                        "display_name": "⭐ Kimi K3 Free (TokenRouter)",
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

## 4. Windows Credential Manager Injection Pattern

Zed on Windows looks up credentials for custom OpenAI-compatible endpoints directly in Windows Credential Manager using the pattern:
```
Target: zed:url=<api_url>
User:   Bearer
Pass:   <api_token>
```

To inject your real TokenRouter key:
```powershell
cmdkey /generic:"zed:url=https://api.tokenrouter.com/v1" /user:"Bearer" /pass:"<YOUR_REAL_TOKENROUTER_API_KEY>"
```

---

## 5. Live Test Matrix (100% Pass)

| Test Category | Description | `kimi-coding` | `moonshotai/kimi-k3-free` | `auto/best-coding` |
| :--- | :--- | :---: | :---: | :---: |
| **1. Plain Chat** | Single-turn instruction | **`PASS`** (200 in 3.42s) | **`PASS`** (200 in 3.61s) | **`PASS`** (200 in 3.40s) |
| **2. Multi-turn Agent** | Multi-turn conversation context | **`PASS`** (200 in 7.58s) | **`PASS`** (200 in 3.76s) | **`PASS`** (200 in 4.09s) |
| **3. Zed Tool Calling** | `tools` schema + `tool_choice: "auto"` | **`PASS`** (200 in 4.15s) | **`PASS`** (200 in 4.34s) | **`PASS`** (200 in 3.58s) |
| **4. Live SSE Streaming** | Token-by-token streaming chunks | **`PASS`** (200, 33 chunks) | **`PASS`** (200, 53 chunks) | **`PASS`** (200, 51 chunks) |
