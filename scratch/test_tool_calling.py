import requests
import json

base_url = "http://localhost:20128/v1/chat/completions"

tools_payload = [
    {
        "type": "function",
        "function": {
            "name": "get_current_weather",
            "description": "Get the current weather in a given location",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {"type": "string", "description": "The city and state"}
                },
                "required": ["location"]
            }
        }
    }
]

models_to_test = [
    "kimi-coding",
    "auto/best-coding",
    "frontier",
    "fusion-coder",
    "nvidia/nemotron-3-super-120b-a12b",
    "nvidia/nemotron-nano-12b-v2-vl",
    "z-ai/glm-5.2",
    "qwen/qwen3-coder-480b-a35b-instruct",
    "mistralai/codestral-22b-instruct-v0.1",
    "openai/gpt-oss-120b",
    "opencode-zen/kimi-k3",
    "openrouter/moonshotai/kimi-k3",
    "ainative/deepseek-v3"
]

for model in models_to_test:
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "What's the weather in Tokyo?"}],
        "tools": tools_payload,
        "tool_choice": "auto",
        "max_tokens": 100
    }
    try:
        r = requests.post(base_url, json=payload, timeout=10)
        print(f"[{model}] Status: {r.status_code}")
        if r.status_code != 200:
            print(f"  Error: {r.text[:200]}")
        else:
            print(f"  Success: {r.text[:150]}")
    except Exception as e:
        print(f"[{model}] Exception: {e}")
