import requests

combos_to_test = [
    "kimi-coding",
    "auto/best-coding",
    "auto/best-reasoning",
    "auto/best-chat",
    "fusion-coder",
    "frontier"
]

tools_payload = [
    {
        "type": "function",
        "function": {
            "name": "get_current_weather",
            "description": "Get current weather in a location",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {"type": "string"}
                },
                "required": ["location"]
            }
        }
    }
]

for name in combos_to_test:
    payload = {
        "model": name,
        "messages": [{"role": "user", "content": "Hi"}],
        "tools": tools_payload,
        "tool_choice": "auto",
        "max_tokens": 50
    }
    try:
        r = requests.post("http://localhost:20128/v1/chat/completions", json=payload, timeout=15)
        print(f"[{name}] Status: {r.status_code}")
    except Exception as e:
        print(f"[{name}] Error: {e}")
