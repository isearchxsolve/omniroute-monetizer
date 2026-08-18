# Final verdict — 295 actual providers

Date: 2026-08-18 (Asia/Calcutta)

## Executive verdict

**Overall provider mission: MONETIZER_BLOCKED.** The 295-provider catalog is inventoried and classified, but the evidence does not support claiming that all 295 providers are authenticated, chat-completable, and live.

**Runtime certification: MONETIZER_READY.** The final acceptance run recorded T1–T20 passed with 0 failures. That certifies the OmniRoute runtime/integration surface; it does not certify every upstream provider.

## Count reconciliation

- state/all_296_providers_execution_ledger.json contains 296 records.
- The services record is excluded from the provider verdict: it is deployed_code / embedded local-services management, with no registry entry, executor, or database connection. It is a meta/service row, not an upstream provider.
- Therefore the authoritative current provider inventory is **295 actual provider slugs**.
- The older state/evidence/gap_analysis.json is not authoritative for this final count: it contains 300 merged slugs, including auto and four slugs absent from the current ledger (alibaba-cn, auto, kimi, kimi-coding-apikey).
- The gemini record is keyed by gemini but lacks an internal slug field; the ledger property key is used as its provider ID.

## Current verdict totals

| Ledger verdict | Count | Share of 295 |
|---|---:|---:|
| AUTHENTICATED_CLOUDFLARE_TLS_BLOCKED | 1 | 0.3% |
| BLOCKED_AUTH_REQUIRED | 7 | 2.4% |
| BLOCKED_CREDITS | 1 | 0.3% |
| BLOCKED_FORBIDDEN | 1 | 0.3% |
| BLOCKED_LOCAL_RUNTIME | 13 | 4.4% |
| BLOCKED_RATE_LIMITED | 1 | 0.3% |
| BLOCKED_UNVERIFIED | 2 | 0.7% |
| BLOCKED_UPSTREAM_DOWN | 3 | 1% |
| BLOCKED_VALIDATION_UNSUPPORTED | 5 | 1.7% |
| BLOCKED_WEB_SESSION | 24 | 8.1% |
| EXTERNAL_ACCOUNT_REQUIRED | 180 | 61% |
| LIVE_ACTIVE | 26 | 8.8% |
| NOT_CHAT_COMPLETABLE | 31 | 10.5% |

The groups below are exhaustive: every one of the 295 actual provider slugs appears once, under its current ledger status.

### AUTHENTICATED_CLOUDFLARE_TLS_BLOCKED — 1
Authenticated provider/session, but upstream Cloudflare TLS or fingerprint protection blocks requests.

- grok-web

### BLOCKED_AUTH_REQUIRED — 7
A configured connection exists, but the credential is missing, invalid, expired, or requires reauthentication.

- deepseek
- friendliai
- huggingface
- opencode-zen
- openrouter
- qoder
- xai-oauth

### BLOCKED_CREDITS — 1
Credential reaches the provider, but quota/credits/rate entitlement is exhausted.

- t3-web

### BLOCKED_FORBIDDEN — 1
Credential reaches the provider, but the upstream returns forbidden/plan/geo denial.

- alibaba

### BLOCKED_LOCAL_RUNTIME — 13
The provider depends on a local runtime/CLI that is not installed or listening.

- cline
- comfyui
- docker-model-runner
- lemonade
- llama-cpp
- llamafile
- lm-studio
- ollama-local
- oobabooga
- sdwebui
- triton
- vllm
- xinference

### BLOCKED_RATE_LIMITED — 1
The upstream currently rate-limits or anti-abuses this source IP/session.

- duckduckgo-web

### BLOCKED_UNVERIFIED — 2
A prior failure or upstream boundary exists, but current evidence is not sufficient to certify the connection.

- chipotle
- theoldllm

### BLOCKED_UPSTREAM_DOWN — 3
The upstream endpoint is unavailable, gone, or currently rejects the requested path/model.

- auggie
- mimocode
- openai

### BLOCKED_VALIDATION_UNSUPPORTED — 5
OmniRoute native validation is unsupported or the selected model/path is not currently certifiable.

- aihorde
- gemini
- nvidia
- trae
- windsurf

### BLOCKED_WEB_SESSION — 24
The provider requires an authenticated browser session/cookie that was not available in the allowed browser context.

- adapta-web
- adobe-firefly
- claude-web
- copilot-m365-web
- copilot-web
- deepseek-web
- doubao-web
- felo-web
- gemini-business
- hailuo-web
- huggingchat
- hyperagent
- inner-ai
- kimi-web
- microsoft-designer-web
- muse-spark-web
- notion-web
- poe-web
- promptql
- qwen-web
- v0-vercel-web
- venice-web
- yuanbao-web
- zenmux-free

### EXTERNAL_ACCOUNT_REQUIRED — 180
No usable connection is configured; user-owned account/key setup is required.

- 360ai
- agentrouter
- ai21
- aimlapi
- ant-ling
- anthropic
- api-airforce
- arcee-ai
- azure-ai
- azure-openai
- bai
- baichuan
- baidu
- bailian-coding-plan
- baseten
- bazaarlink
- bedrock
- black-forest-labs
- blackbox
- bluesminds
- byteplus
- bytez
- charm-hyper
- chenzk
- chutes
- clarifai
- claude
- clova-studio
- codebuddy-cn
- codestral
- command-code
- coze
- crof
- cursor
- dahl
- databricks
- datarobot
- deepinfra
- devin-cli
- dgrid
- dify
- digitalocean
- dit
- doubao
- empower
- factory
- fal-ai
- featherless-ai
- fenayai
- fireworks
- freeaiapikey
- freemodel-dev
- freepik
- freetheai
- g4f-gemini
- g4f-groq
- g4f-nvidia
- g4f-ollama
- g4f-pollinations
- galadriel
- getgoapi
- ghe-copilot
- gigachat
- github-models
- gitlab
- gitlab-duo
- gitlawb
- gitlawb-gmi
- glm
- glm-cn
- glmt
- hackclub
- haiper
- hcnsec
- heroku
- hyperbolic
- ideogram
- iflytek
- inception
- inference-net
- internlm
- jina-ai
- kenari
- kie
- kilo-gateway
- lambda-ai
- laozhang
- leonardo
- liquid
- llamagate
- longcat
- maritalk
- meta-llama
- minimax
- minimax-cn
- mistral
- mixedbread
- modal
- modelscope
- monsterapi
- moonshot
- morph
- nanogpt
- navy
- nebius
- nlpcloud
- nomic
- nous-research
- novita
- nscale
- nube
- oci
- ollama-cloud
- openadapter
- opencode-go
- openvecta
- orcarouter
- ovhcloud
- perplexity
- piapi
- pioneer
- plamo
- poe
- pollinations
- predibase
- publicai
- puter
- qianfan
- qiniu
- qwen-cloud
- qwen-cloud-token-plan
- recraft
- reka
- requesty
- routeway
- runwayml
- sambanova
- sap
- sarvam
- scaleway
- sealion
- segmind
- sensenova
- siliconflow
- snowflake
- sparkdesk
- stability-ai
- stepfun
- sumopod
- suno
- synthetic
- tencent
- thebai
- together
- tokenrouter
- topaz
- typhoon
- udio
- uncloseai
- upstage
- v0-vercel
- venice
- vercel-ai-gateway
- vertex
- vertex-partner
- volcengine
- voyage-ai
- wafer
- wandb
- watsonx
- writer
- x5lab
- xai
- xiaomi-mimo
- xiaomi-mimo-token-plan
- yi
- zai
- zed
- zed-hosted
- zenmux

### LIVE_ACTIVE — 26
Ledger marks the provider active; this is a state label, not a claim that every provider received a fresh final E2E content probe.

- agnes
- agy
- ainative
- aion
- amazon-q
- antigravity
- blackbox-web
- cerebras
- chatgpt-web
- clinepass
- cloudflare-ai
- codex
- cohere
- gemini-web
- github
- grok-cli
- groq
- kilocode
- kimi-coding
- kiro
- llm7
- lmarena
- nara
- opencode
- perplexity-web
- zai-web

### NOT_CHAT_COMPLETABLE — 31
Provider is a non-chat service (search, audio, image, video, or other non-LLM path) for this acceptance target.

- 9router
- assemblyai
- aws-polly
- brave-search
- cartesia
- cliproxyapi
- codex-cloud
- deepgram
- devin
- elevenlabs
- exa-search
- firecrawl
- fishaudio
- gladia
- google-pse-search
- inworld
- jina-reader
- jules
- linkup-search
- ollama-search
- perplexity-search
- playht
- rev-ai
- searchapi-search
- searxng-search
- serper-search
- speechmatics
- tavily-search
- tinyfish
- veoaifree-web
- youcom-search

## Evidence-strength notes

- The latest dynamic E2E artifact contains 13 non-empty HTTP 200 probes; the separately logged OpenCode remediation adds a non-empty local E2E HTTP 200 proof. Those 14 names are:

- agnes, aion, blackbox-web, cerebras, chatgpt-web, cloudflare-ai, codex, cohere, gemini-web, groq, kilocode, kiro, llm7, opencode

- The ledger marks 26 entries LIVE_ACTIVE, but the final suite does not issue a fresh chat-completion probe to all 26. I therefore preserve LIVE_ACTIVE as the ledger state and do not rewrite it as 26 freshly E2E-verified providers.
- No provider key, OAuth token, browser cookie, or placeholder credential was fabricated or logged.
- OpenCode is the completed remediation in this handoff: upstream model-list HTTP 200, native OmniRoute test valid=true, and local chat completion HTTP 200 with non-empty content.

## Final disposition

The system is operational and certified at the OmniRoute/runtime level, but the all-provider monetizer objective is not complete. The correct final disposition is MONETIZER_BLOCKED, with the blocker classes above preserved as actionable, evidence-backed outcomes.

Source ledger: state/all_296_providers_execution_ledger.json


