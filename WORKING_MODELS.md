# WORKING MODELS LIST

Generated from measured probes, not from catalogue listings. A route counts as working only
when the model returned real generated content.

## The short answer

- **Chat / text: 296 routes work**, across **36 providers**.
- **Video: 0 routes proven.** See below -- this is the current focus.

Chat source: `state/healthy_provider_models_rescan.json`, probed 2026-08-23T07:16 UTC.
115 connections tested, 69 healthy,
3907 candidate routes tried, 296 confirmed by a real completion.

## VIDEO -- the current focus

**Proven working video models: 0.** Only one video generation has ever been attempted:
`kie/grok-imagine/text-to-video` on 2026-08-22, which returned
HTTP 502 -- "HTTP 502: Credits insufficient : Your current balance isn’t enough to run this request. Please top up to continue.". No other video model has been tried.

Video models that EXIST and are already wired -- the ones to prove next:

| provider | connection | video models |
|---|---|---|
| **segmind** | ACTIVE, key stored | `wan2.1-t2v`, `wan2.7-i2v`, `hunyuan-video-t2v`, `ltx-video-t2v`, `kling-video-t2v` |
| kie | ACTIVE | **none mapped** -- its 17 routes are Claude/GPT/Gemini text plus 6 ElevenLabs audio models. The `grok-imagine/text-to-video` route that was tried is not in OmniRoute's kie catalogue at all. |
| fal-ai | **INACTIVE** | none -- all 12 routes are image-only (flux, seedream, ideogram, recraft) |
| pollinations | ACTIVE | image only (`zimage`, `qwen-image-3`, `grok-imagine-image-2.0`); the `pollinations-video` handler is missing in OmniRoute |

**So segmind is the only provider with real text-to-video routes wired and ready to test.**
Five of its eleven routes are video; the other six are image (flux, sdxl, sd3.5, kandinsky).

## CHAT / TEXT -- confirmed working, by provider

Use these exactly as written, including the provider prefix.

### openadapter (27)
- `openadapter/0G-DeepSeek-V3`
- `openadapter/0GM-1.0-35B-A3B`
- `openadapter/DeepSeek-V4-Flash`
- `openadapter/DeepSeek-V4-Pro`
- `openadapter/GLM-5`
- `openadapter/GPT-20-OSS`
- `openadapter/GPT-5.6-Luna`
- `openadapter/Gemma-2-27B`
- `openadapter/Gemma-3-12B`
- `openadapter/Gemma-3-27B`
- `openadapter/Gemma-4-31B-TEE`
- `openadapter/Hermes-4-14B`
- `openadapter/Hermes-4-405B`
- `openadapter/Hy3`
- `openadapter/Kimi-K2`
- `openadapter/Kimi-K2-Think`
- `openadapter/Kimi-K2.5`
- `openadapter/Llama-3.1-8B`
- `openadapter/Llama-3.2-Vision-90B`
- `openadapter/M2-HerOS2`
- `openadapter/Mathstral-7B`
- `openadapter/MiniMax-M2.5-TEE`
- `openadapter/Nemotron-3-Super-120B`
- `openadapter/OA-Robin-Mini-Preview`
- `openadapter/Qwen2.5-Coder`
- `openadapter/Qwen3.5-122B`
- `openadapter/Qwen3.5-VL`

### agy (12)
- `agy/gemini-2.5-flash`
- `agy/gemini-2.5-flash-lite`
- `agy/gemini-2.5-flash-thinking`
- `agy/gemini-3.1-flash-lite`
- `agy/gemini-3.1-pro-low`
- `agy/gemini-3.5-flash-low`
- `agy/gemini-3.6-flash-high`
- `agy/gemini-3.6-flash-low`
- `agy/gemini-3.6-flash-medium`
- `agy/gemini-3.6-flash-tiered`
- `agy/gemini-3.7-flash-tiered`
- `agy/gemini-pro-agent`

### requesty (23)
- `requesty/alibaba/qwen-max`
- `requesty/alibaba/qwen3-30b-a3b-instruct-2507`
- `requesty/alibaba/qwen3-coder-flash`
- `requesty/alibaba/qwen3-coder-plus`
- `requesty/alibaba/qwen3-max`
- `requesty/alibaba/qwen3.6-plus`
- `requesty/google/gemini-3.1-flash-lite`
- `requesty/mistral/codestral-latest`
- `requesty/mistral/devstral-latest`
- `requesty/mistral/devstral-small-latest`
- `requesty/mistral/mistral-large-latest`
- `requesty/mistral/mistral-medium-3-5`
- `requesty/mistral/mistral-medium-latest`
- `requesty/mistral/mistral-small-2503`
- `requesty/mistral/mistral-small-2603`
- `requesty/mistral/mistral-small-latest`
- `requesty/mistral/open-mistral-7b`
- `requesty/nvidia/nemotron-3-nano-30b-a3b`
- `requesty/nvidia/nemotron-3-nano-omni-30b-a3b-reasoning`
- `requesty/nvidia/nemotron-3-super-120b-a12b`
- `requesty/nvidia/nemotron-3.5-content-safety`
- `requesty/openai/gpt-5.1`
- `requesty/openai/gpt-5.2`

### antigravity (7)
- `antigravity/gemini-2.5-flash-thinking`
- `antigravity/gemini-3.1-pro-low`
- `antigravity/gemini-3.5-flash-low`
- `antigravity/gemini-3.6-flash-high`
- `antigravity/gemini-3.6-flash-low`
- `antigravity/gemini-3.6-flash-medium`
- `antigravity/gemini-pro-agent`

### mistral (20)
- `mistral/codestral-latest`
- `mistral/devstral-2512`
- `mistral/devstral-latest`
- `mistral/magistral-small-latest`
- `mistral/ministral-14b-latest`
- `mistral/ministral-3b-latest`
- `mistral/ministral-8b-latest`
- `mistral/mistral-code-agent-latest`
- `mistral/mistral-code-fim-latest`
- `mistral/mistral-code-latest`
- `mistral/mistral-medium-2505`
- `mistral/mistral-medium-2508`
- `mistral/mistral-medium-2604`
- `mistral/mistral-medium-latest`
- `mistral/mistral-small-latest`
- `mistral/mistral-vibe-cli-fast`
- `mistral/mistral-vibe-cli-latest`
- `mistral/mistral-vibe-cli-with-tools`
- `mistral/voxtral-small-2507`
- `mistral/voxtral-small-latest`

### openrouter (20)
- `openrouter/aion-labs/aion-2.0`
- `openrouter/aion-labs/aion-3.0`
- `openrouter/aion-labs/aion-3.0-mini`
- `openrouter/aion-labs/aion-rp-llama-3.1-8b`
- `openrouter/cohere/command-r-08-2024`
- `openrouter/cohere/command-r-plus-08-2024`
- `openrouter/google/gemini-3.1-flash-lite`
- `openrouter/google/gemma-4-31b-it:free`
- `openrouter/morph/morph-v3-fast`
- `openrouter/morph/morph-v3-large`
- `openrouter/nvidia/nemotron-3-nano-30b-a3b`
- `openrouter/nvidia/nemotron-3-super-120b-a12b`
- `openrouter/openai/gpt-5.2`
- `openrouter/openai/gpt-5.2-codex`
- `openrouter/openai/gpt-5.3-codex`
- `openrouter/openrouter/free`
- `openrouter/perplexity/sonar-pro-search`
- `openrouter/x-ai/grok-4.20`
- `openrouter/x-ai/grok-4.3`
- `openrouter/x-ai/grok-4.5`

### inference-net (19)
- `inference-net/claude-opus-5`
- `inference-net/deepseek-v4-flash`
- `inference-net/deepseek-v4-pro`
- `inference-net/gemini-2.5-flash`
- `inference-net/gemini-2.5-flash-lite`
- `inference-net/gemini-3.1-flash-lite`
- `inference-net/gemini-3.5-flash-lite`
- `inference-net/gpt-4.1`
- `inference-net/gpt-4.1-mini`
- `inference-net/gpt-4.1-nano`
- `inference-net/gpt-4o`
- `inference-net/gpt-4o-mini`
- `inference-net/gpt-5.4`
- `inference-net/gpt-5.5`
- `inference-net/gpt-5.6-luna`
- `inference-net/gpt-5.6-sol`
- `inference-net/gpt-5.6-terra`
- `inference-net/grok-4.5`
- `inference-net/grok-4.6`

### kilocode (14)
- `kilocode/aion-labs/aion-2.0`
- `kilocode/aion-labs/aion-3.0`
- `kilocode/aion-labs/aion-3.0-mini`
- `kilocode/aion-labs/aion-rp-llama-3.1-8b`
- `kilocode/cohere/command-r-08-2024`
- `kilocode/cohere/command-r-plus-08-2024`
- `kilocode/cohere/command-r7b-12-2024`
- `kilocode/google/gemini-3.1-flash-lite`
- `kilocode/morph/morph-v3-fast`
- `kilocode/morph/morph-v3-large`
- `kilocode/nvidia/nemotron-3-nano-30b-a3b`
- `kilocode/nvidia/nemotron-3-super-120b-a12b`
- `kilocode/openrouter/free`
- `kilocode/x-ai/grok-4.5`

### llm7 (14)
- `llm7/claude-fable-5`
- `llm7/claude-opus-5`
- `llm7/claude-sonnet-5`
- `llm7/codestral-latest`
- `llm7/gemini-3.1-flash-lite`
- `llm7/gemini-3.5-flash-low`
- `llm7/gpt-5.4`
- `llm7/gpt-5.4-mini`
- `llm7/gpt-5.5`
- `llm7/gpt-5.6-sol`
- `llm7/gpt-5.6-terra`
- `llm7/grok-4.5`
- `llm7/grok-4.6`
- `llm7/mistral-Small-24B-Instruct-2501`

### nvidia (14)
- `nvidia/meta/llama-3.1-8b-instruct`
- `nvidia/meta/llama-3.2-11b-vision-instruct`
- `nvidia/meta/llama-3.2-90b-vision-instruct`
- `nvidia/mistralai/mistral-nemotron`
- `nvidia/nvidia/llama-3.1-nemoguard-8b-content-safety`
- `nvidia/nvidia/llama-3.1-nemoguard-8b-topic-control`
- `nvidia/nvidia/llama-3.1-nemotron-nano-vl-8b-v1`
- `nvidia/nvidia/llama-3.1-nemotron-safety-guard-8b-v3`
- `nvidia/nvidia/nemotron-3-nano-30b-a3b`
- `nvidia/nvidia/nemotron-3-nano-omni-30b-a3b-reasoning`
- `nvidia/nvidia/nemotron-3-super-120b-a12b`
- `nvidia/nvidia/nemotron-3.5-content-safety`
- `nvidia/nvidia/nemotron-mini-4b-instruct`
- `nvidia/nvidia/nemotron-nano-12b-v2-vl`

### ainative (11)
- `ainative/claude-opus-4`
- `ainative/deepseek-3.2`
- `ainative/deepseek-v3.2`
- `ainative/deepseek-v4-pro`
- `ainative/gpt-4o`
- `ainative/gpt-4o-mini`
- `ainative/kimi-k2`
- `ainative/kimi-k2-thinking`
- `ainative/llama-4-maverick`
- `ainative/llama-4-scout`
- `ainative/mimo-v2.5-pro`

### nous-research (11)
- `nous-research/aion-labs/aion-2.0`
- `nous-research/aion-labs/aion-3.0`
- `nous-research/aion-labs/aion-3.0-mini`
- `nous-research/cohere/command-r-08-2024`
- `nous-research/cohere/command-r-plus-08-2024`
- `nous-research/google/gemini-3.1-flash-lite`
- `nous-research/nvidia/nemotron-3-nano-30b-a3b`
- `nous-research/nvidia/nemotron-3-super-120b-a12b`
- `nous-research/x-ai/grok-4.20`
- `nous-research/x-ai/grok-4.3`
- `nous-research/x-ai/grok-4.5`

### cohere (8)
- `cohere/c4ai-aya-expanse-32b`
- `cohere/c4ai-aya-vision-32b`
- `cohere/command-a-03-2025`
- `cohere/command-a-plus-05-2026`
- `cohere/command-a-reasoning-08-2025`
- `cohere/command-a-translate-08-2025`
- `cohere/command-a-vision-07-2025`
- `cohere/command-r7b-arabic-02-2025`

### t3-web (8)
- `t3-web/claude-opus-4`
- `t3-web/claude-sonnet-4`
- `t3-web/gemini-2.5-flash`
- `t3-web/gpt-4.1`
- `t3-web/gpt-4o`
- `t3-web/kimi-k2`
- `t3-web/llama-4-maverick`
- `t3-web/llama-4-scout`

### opencode-zen (6)
- `opencode-zen/big-pickle`
- `opencode-zen/gemini-3.1-pro`
- `opencode-zen/hy3-free`
- `opencode-zen/laguna-s-2.1-free`
- `opencode-zen/nemotron-3.5-lightning-free`
- `opencode-zen/qwen3.5-plus`

### cloudflare-ai (5)
- `cloudflare-ai/@cf/meta/llama-3.2-3b-instruct`
- `cloudflare-ai/@cf/meta/llama-3.3-70b-instruct-fp8-fast`
- `cloudflare-ai/@cf/mistral/mistral-7b-instruct-v0.2-lora`
- `cloudflare-ai/@cf/qwen/qwen2.5-coder-32b-instruct`
- `cloudflare-ai/@cf/qwen/qwq-32b`

### lmarena (5)
- `lmarena/claude-sonnet-5`
- `lmarena/gemini-3.1-flash-lite`
- `lmarena/glm-5.1`
- `lmarena/hy3`
- `lmarena/qwen3.7-max`

### aion (4)
- `aion/aion-labs/aion-2.0`
- `aion/aion-labs/aion-3.0`
- `aion/aion-labs/aion-3.0-mini`
- `aion/aion-labs/aion-rp-llama-3.1-8b`

### bazaarlink (4)
- `bazaarlink/claude-sonnet-4.5`
- `bazaarlink/claude-sonnet-4.6`
- `bazaarlink/gemini-3.1-flash-lite-preview`
- `bazaarlink/qwen3.7-max`

### chatgpt-web (4)
- `chatgpt-web/gpt-5.5-pro-extended`
- `chatgpt-web/gpt-5.5-thinking`
- `chatgpt-web/gpt-5.6-pro`
- `chatgpt-web/gpt-5.6-thinking`

### kiro (4)
- `kiro/auto`
- `kiro/claude-sonnet-4.5`
- `kiro/deepseek-3.2`
- `kiro/qwen3-coder-next`

### reka (2)
- `reka/reka-edge-2603`
- `reka/reka-flash`

### orcarouter (3)
- `orcarouter/deepseek/deepseek-chat`
- `orcarouter/google/gemini-2.5-flash`
- `orcarouter/google/gemini-3.1-flash-lite`

### publicai (3)
- `publicai/aisingapore/Gemma-SEA-LION-v4-27B-IT`
- `publicai/aisingapore/Qwen-SEA-LION-v4-32B-IT`
- `publicai/swiss-ai/apertus-70b-instruct`

### sealion (3)
- `sealion/aisingapore/Gemma-SEA-LION-v4-27B-IT`
- `sealion/aisingapore/Llama-SEA-LION-v3-70B-IT`
- `sealion/aisingapore/Qwen-SEA-LION-v4-32B-IT`

### agentrouter (2)
- `agentrouter/claude-opus-5`
- `agentrouter/gpt-5.6-sol`

### aimlapi (2)
- `aimlapi/deepseek-chat`
- `aimlapi/gpt-4o`

### alibaba (2)
- `alibaba/qwen3.5-plus`
- `alibaba/qwen3.7-max`

### gemini (2)
- `gemini/gemini-3.1-flash-lite-preview`
- `gemini/gemini-robotics-er-1.6-preview`

### pollinations (2)
- `pollinations/mimo-v2.5-pro`
- `pollinations/qwen3.7-max`

### vertex (2)
- `vertex/gemini-3.1-flash-lite-preview`
- `vertex/gemini-robotics-er-1.6-preview`

### deepinfra (1)
- `deepinfra/google/gemini-3.1-flash-lite`

### g4f-nvidia (1)
- `g4f-nvidia/nvidia/nemotron-3-nano-30b-a3b`

### github (1)
- `github/claude-sonnet-4.6`

### morph (1)
- `morph/morph-dsv4flash`

### novita (1)
- `novita/nvidia/nemotron-3-nano-30b-a3b`
