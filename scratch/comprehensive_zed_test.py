import requests
import json
import time

base_url = "http://localhost:20128/v1/chat/completions"

models_to_test = [
    "kimi-coding",
    "moonshotai/kimi-k3-free",
    "auto/best-coding"
]

tools_schema = [
    {
        "type": "function",
        "function": {
            "name": "edit_file",
            "description": "Edit lines of a file",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"}
                },
                "required": ["path", "content"]
            }
        }
    }
]

print("==================================================")
print("     COMPREHENSIVE ZED / OMNIROUTE TEST SUITE     ")
print("==================================================")

results = {}

for model in models_to_test:
    print(f"\n[TESTING MODEL: {model}]")
    
    # 1. Plain Chat Completion (Non-streaming)
    t0 = time.time()
    p1 = {
        "model": model,
        "messages": [{"role": "user", "content": "Write a 1-line Python lambda to square a number."}],
        "max_tokens": 60,
        "stream": False
    }
    r1 = requests.post(base_url, json=p1, timeout=15)
    dt1 = time.time() - t0
    status1 = r1.status_code == 200
    print(f"  1. Plain Chat: {'PASS' if status1 else 'FAIL'} ({r1.status_code} in {dt1:.2f}s)")
    if not status1:
        print(f"     Error: {r1.text[:200]}")
        
    # 2. Multi-turn Agent Context
    t0 = time.time()
    p2 = {
        "model": model,
        "messages": [
            {"role": "user", "content": "Hello, I am testing the code editor integration."},
            {"role": "assistant", "content": "Understood! How can I assist you with your code?"},
            {"role": "user", "content": "Give me a quick 3-step checklist for Python code review."}
        ],
        "max_tokens": 100,
        "stream": False
    }
    r2 = requests.post(base_url, json=p2, timeout=15)
    dt2 = time.time() - t0
    status2 = r2.status_code == 200
    print(f"  2. Multi-turn Context: {'PASS' if status2 else 'FAIL'} ({r2.status_code} in {dt2:.2f}s)")
    if not status2:
        print(f"     Error: {r2.text[:200]}")

    # 3. Tool Calling / Function Calling (Zed Agent Mode)
    t0 = time.time()
    p3 = {
        "model": model,
        "messages": [{"role": "user", "content": "Please edit file app.py to add print('hello')"}],
        "tools": tools_schema,
        "tool_choice": "auto",
        "max_tokens": 100,
        "stream": False
    }
    r3 = requests.post(base_url, json=p3, timeout=15)
    dt3 = time.time() - t0
    status3 = r3.status_code == 200
    print(f"  3. Tool Calling (Zed Agent): {'PASS' if status3 else 'FAIL'} ({r3.status_code} in {dt3:.2f}s)")
    if not status3:
        print(f"     Error: {r3.text[:200]}")

    # 4. Live Streaming (SSE)
    t0 = time.time()
    p4 = {
        "model": model,
        "messages": [{"role": "user", "content": "Say: 'VERIFICATION_SUCCESSFUL'"}],
        "max_tokens": 40,
        "stream": True
    }
    r4 = requests.post(base_url, json=p4, timeout=15, stream=True)
    chunks = 0
    sample_text = ""
    for line in r4.iter_lines():
        if line:
            chunks += 1
            decoded = line.decode('utf-8')
            if "content" in decoded or "reasoning" in decoded:
                sample_text += decoded[:60]
    dt4 = time.time() - t0
    status4 = r4.status_code == 200 and chunks > 0
    print(f"  4. Live Streaming (SSE): {'PASS' if status4 else 'FAIL'} ({r4.status_code}, {chunks} chunks in {dt4:.2f}s)")

    all_passed = status1 and status2 and status3 and status4
    results[model] = all_passed

print("\n==================================================")
print("                  FINAL SUMMARY                   ")
print("==================================================")
for m, passed in results.items():
    print(f"  [{m}]: {'ALL TESTS PASSED (100%)' if passed else 'FAILED'}")
