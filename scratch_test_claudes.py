import requests

models = [
    "antigravity/claude-3-5-sonnet",
    "openrouter/anthropic/claude-3.5-sonnet",
    "bazaarlink/claude-3-haiku",
    "kilocode/anthropic/claude-3-haiku",
    "t3-web/claude-3.7",
    "cl/anthropic/claude-3-haiku",
    "cline/anthropic/claude-3-haiku",
    "kc/anthropic/claude-3-haiku",
    "nous/anthropic/claude-3-haiku",
    "nous-research/anthropic/claude-3-haiku"
]

for m in models:
    try:
        r = requests.post(
            'http://127.0.0.1:20128/v1/messages', 
            headers={'x-api-key':'sk-omniroute','anthropic-version':'2023-06-01'}, 
            json={'model': m, 'max_tokens':10, 'messages':[{'role':'user', 'content':'hi'}]},
            timeout=5
        )
        if r.status_code == 200:
            print(f"[SUCCESS] {m}")
        else:
            print(f"[FAIL {r.status_code}] {m} - {r.text[:100]}")
    except Exception as e:
        print(f"[ERROR] {m} - {e}")
