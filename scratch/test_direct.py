import requests, json

BASE_URL = 'http://localhost:20128'
headers = {
    "Authorization": "Bearer any",
    "Content-Type": "application/json"
}

def test_model(model_name):
    payload = {
        "model": model_name,
        "messages": [
            {"role": "user", "content": "Hello!"}
        ]
    }
    print(f"Testing {model_name} directly...")
    try:
        resp = requests.post(f"{BASE_URL}/v1/chat/completions", headers=headers, json=payload, timeout=20)
        print(f"Status: {resp.status_code}")
        if resp.status_code != 200:
            print(f"Error: {resp.text[:200]}")
        else:
            print(f"Success! Model used: {resp.json().get('model')}")
    except Exception as e:
        print(f"Exception: {e}")

print("--- Testing via Combo ---")
test_model("frontier")

print("\n--- Testing Models Directly ---")
test_model("z-ai/glm-5.2")
test_model("openai/gpt-5.6-sol")
