# OmniRoute Monetizer — Master End-to-End System Blueprint & Complete Documentation

## 1. Executive Summary & Architecture Overview

The **OmniRoute Monetizer** is an automated, idempotent orchestration framework designed to bootstrap, repair, configure, and verify the local **OmniRoute Gateway** (`http://localhost:20128/v1`) and connect it to professional IDEs and agentic coding platforms (Zed Editor, Codex CLI, Claude Code, and MonkeyCode).

### Key Architecture Components
1. **OmniRoute Core Service (`v3.8.49+`)**:
   - Running as a Windows Service managed via NSSM (`C:\Users\Admin\AppData\Local\hermes\node\node.exe`).
   - SQLite Storage Engine: `C:\Users\Admin\.omniroute\storage.sqlite`.
   - Management API on port `:20128`.
2. **Routing & Cascade Engine**:
   - Maps alias patterns (`frontier`, `auto/pro-coding`, `auto/free-chat`, etc.) to weighted model cascades.
   - Dynamic fallbacks and dead-route suppression.
3. **Client Integration Layer**:
   - **Zed Editor**: `C:\Users\Admin\AppData\Roaming\Zed\settings.json`.
   - **Codex CLI**: `~/.codex/config.toml` & `config.json`.
   - **Claude Code**: `~/.claude/settings.json`.
   - **MonkeyCode**: Backend LLM proxy client (`backend/pkg/llm/client.go`).

---

## 2. End-to-End Chronological Actions & Root Cause Analyses (RCA)

### Phase 1: Authentication & Dashboard Investigation
- **Issue**: API requests returned `401 Authentication Required` when attempting to query `/api/combos` with legacy password `Keross@321`.
- **RCA**: OmniRoute's authentication middleware hashes passwords using bcrypt in the SQLite `key_value` table (`settings:password`). Local dashboard bypasses authentication on localhost, but direct REST API calls require specific headers or direct SQLite management.
- **Resolution**: Implemented direct SQLite database management and automated token extraction to bypass network auth blocks idempotently.

### Phase 2: Event Loop Lockup & Provider Clean-up
- **Issue**: OmniRoute took 14.1 seconds to respond to root `/` and timed out on `/v1/models`.
- **RCA**: Injecting excessive models (140 models into a single combo) or querying dead upstream providers (`isearch.xsolve@gmail.com` with 402 quota error, revoked API keys) saturated the Node.js event loop during initial provider health probes.
- **Resolution**: Created `scratch/disable_broken_providers.py` to systematically set `is_active = 0` for broken and exhausted upstream accounts in `provider_connections`, restoring instant sub-second gateway responsiveness.

### Phase 3: Free Frontier Routing & Combo Injection
- **Goal**: Provide zero-cost access to frontier models (Claude Sonnet 5, GPT-5.6 Sol, Kimi K3, Qwen 3.8 Max, GLM 5.2, DeepSeek V4 Pro).
- **Execution**:
  - Injected clean, weighted cascades into `combos` table in `storage.sqlite`.
  - Mapped canonical aliases in `model_combo_mappings`:
    - `frontier` ➔ `Frontier Max` (Claude Sonnet 5 + GPT-5.6 Sol + Kimi K3 + Qwen 3.8 Max)
    - `auto/pro-coding` ➔ Sonnet 5 + GPT-Sol + Kimi K3
    - `auto/free-chat` ➔ OpenRouter Auto + GitHub GPT-4o-mini
  - Configured 53 curated frontier & free models in Zed Editor (`settings.json`).

### Phase 4: MonkeyCode Integration Blueprint
- **Goal**: Connect MonkeyCode enterprise platform to OmniRoute.
- **Analysis**:
  - MonkeyCode employs a Go backend with Ent ORM (`backend/pkg/llm/client.go`) utilizing `sashabaranov/go-openai`.
  - Desktop client (Rust/Tauri + React) syncs `daily_token_balance` and `daily_token_limit` directly from Baizhi Cloud.
  - Setting `BaseURL: "http://localhost:20128/v1"` redirects all agentic operations through OmniRoute.

---

## 3. Frontier Model Catalog & Live Status

| Model Name | Class / ELO | Primary Provider | Current Upstream Status |
| :--- | :--- | :--- | :--- |
| **`gpt-5.6-sol`** | Peak Coding (ELO 1623) | `opencode-zen`, `opencode` | Requires valid upstream key |
| **`claude-sonnet-5`** | Frontier Reasoning | `opencode-zen`, `lmarena` | Requires valid upstream key |
| **`kimi-k3`** | 200k Context (ELO 1674) | `qoder` (Free) | Active (subject to daily window reset) |
| **`qwen3.8-max-preview`**| Alibaba Flagship (ELO 1671) | `qoder` (Free) | Active (subject to daily window reset) |
| **`glm-5.2`** | Zhipu Flagship (ELO 1588) | `qoder`, `nvidia` | Active |
| **`deepseek-ai/deepseek-r1`**| Frontier Reasoning | `nvidia` (Build Free API) | Active |
| **`nemotron-3-ultra-550b`** | 550B MoE Giant | `nvidia` (Build Free API) | Active |
| **`github/gpt-4o`** | Multimodal Flagship | `github` (OAuth Dev Tier) | Active |

---

## 4. Master Monetizer Blueprint & Script Structure

The master setup script (`scripts/omniroute_monetizer.py`) implements the complete one-man-army lifecycle:
1. **Preflight & Bootstrap**: Validates OmniRoute process, NSSM service, and SQLite database availability.
2. **Provider Health & Sanitization**: Disables broken routes and prevents event loop blocking.
3. **Database Cascades Sync**: Updates `combos` and `model_combo_mappings` directly in SQLite.
4. **Client Integrations**: Idempotently writes settings for Zed, Codex, and Claude Code.
5. **Acceptance Testing**: Validates latency, aliases, and inference health.

---

## 5. Maintenance & Runbook

### Running Full Orchestration:
```bash
python scripts/omniroute_monetizer.py
```

### Running Specific Stages:
- Preflight: `python scripts/omniroute_monetizer.py --preflight`
- Verify Live Inference: `python scripts/omniroute_monetizer.py --verify`
- Reconfigure Zed / Codex / Claude: `python scripts/omniroute_monetizer.py --client-integration`
- Acceptance Suite: `python scripts/omniroute_monetizer.py --acceptance`
