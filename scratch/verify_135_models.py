import json
import time
import urllib.request
import urllib.error
from pathlib import Path

V1_URL = "http://localhost:20128/v1"
API_KEY = "" # Not needed if using localhost directly and REQUIRE_API_KEY is false, but we can rely on standard behavior

def http_request(method, url, body=None, headers=None, timeout=30):
    hdrs = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "omniroute-monetizer-verifier/1.0",
    }
    if headers:
        hdrs.update(headers)
        
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
    
    start = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read().decode("utf-8", errors="replace")
            elapsed = time.monotonic() - start
            try:
                return r.status, json.loads(raw), elapsed
            except json.JSONDecodeError:
                return r.status, {"raw": raw[:8000]}, elapsed
    except urllib.error.HTTPError as e:
        elapsed = time.monotonic() - start
        raw = ""
        try:
            raw = e.read().decode("utf-8", errors="replace")[:4000]
        except Exception:
            pass
        try:
            payload = json.loads(raw)
        except Exception:
            payload = {"raw": raw}
        return e.code, payload, elapsed
    except urllib.error.URLError as e:
        elapsed = time.monotonic() - start
        return 0, {"error": str(e.reason)}, elapsed
    except Exception as e:
        elapsed = time.monotonic() - start
        return 0, {"error": str(e)}, elapsed

def chat_probe(model, prompt="Please respond with exactly the word OK and nothing else.", max_tokens=50, timeout=20):
    body = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": 0,
        "stream": False,
    }
    return http_request("POST", f"{V1_URL}/chat/completions", body=body, timeout=timeout)

def main():
    print("=== Safely Verifying Curated Frontier Models ===")
    
    curated_file = Path(r"C:\Users\Admin\.gemini\antigravity-ide\brain\66113465-2986-4b2f-a97a-0f5e23d17c33\curated_models.md")
    if not curated_file.exists():
        print(f"Error: {curated_file} not found")
        return
        
    content = curated_file.read_text(encoding="utf-8")
    
    models_to_test = []
    current_provider = None
    for line in content.splitlines():
        line = line.strip()
        if line.startswith("### "):
            current_provider = line[4:].strip()
        elif line.startswith("- `") and line.endswith("`"):
            model_id = line[3:-1]
            if current_provider:
                if current_provider == "openrouter":
                    full_id = model_id
                else:
                    full_id = f"{current_provider}/{model_id}" if "/" not in model_id else model_id
                models_to_test.append(full_id)
                
    print(f"Found {len(models_to_test)} models to verify.")
    
    results = {"pass": [], "fail": []}
    
    for i, model in enumerate(models_to_test, 1):
        print(f"[{i}/{len(models_to_test)}] Probing: {model} ...", end=" ", flush=True)
        status, body, elapsed = chat_probe(model)
        
        if status == 200:
            print(f"OK ({elapsed:.2f}s)")
            results["pass"].append({"model": model, "latency": round(elapsed, 2)})
        else:
            err_msg = str(body)[:60].replace('\n', ' ')
            print(f"FAIL (HTTP {status}) - {err_msg}")
            results["fail"].append({"model": model, "status": status, "error": err_msg})
            
        # Throttling to avoid rate-limits (mass-probe prevention)
        time.sleep(1.0)
        
    print(f"\nVerification Complete. Passed: {len(results['pass'])}, Failed: {len(results['fail'])}")
    
    # Generate verification report
    report_lines = [
        "# 135 Model Safe Verification Results",
        f"**Passed:** {len(results['pass'])} | **Failed:** {len(results['fail'])}",
        "",
        "## ✅ Healthy Models (200 OK)",
        ""
    ]
    
    for r in results["pass"]:
        report_lines.append(f"- `{r['model']}` (Latency: {r['latency']}s)")
        
    report_lines.extend([
        "",
        "## ❌ Failed Models",
        ""
    ])
    
    for r in results["fail"]:
        report_lines.append(f"- `{r['model']}` — HTTP {r['status']}: `{r['error']}`")
        
    report_path = Path(r"C:\Users\Admin\.gemini\antigravity-ide\brain\66113465-2986-4b2f-a97a-0f5e23d17c33\verification_results.md")
    report_path.write_text("\n".join(report_lines), encoding="utf-8")
    print(f"Report saved to {report_path}")

if __name__ == "__main__":
    main()
