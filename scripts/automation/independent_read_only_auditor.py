import os
import json
import urllib.request
from datetime import datetime

ROOT_DIR = r"D:\omniroute-monetizer"
API_URL = "http://localhost:20128/v1/chat/completions"

# Using a specialized reasoning combo for a neutral, objective audit
MODEL = "auto/best-reasoning" 
API_KEY = "sk-omniroute"

# Only target the documentation and audit artifacts, strictly READ ONLY
TARGET_ARTIFACTS = [
    os.path.join(ROOT_DIR, "AUDITOR_VERDICT.md"),
    os.path.join(ROOT_DIR, "MASTER_WORKLOG.md"),
    os.path.join(ROOT_DIR, "SIXTH_WORKLOG.md"),
    os.path.join(ROOT_DIR, "artifacts", "final_execution_report.md"),
    os.path.join(ROOT_DIR, "artifacts", "walkthrough.md")
]

SYSTEM_PROMPT = """You are an independent, read-only AI Auditor. 
Your sole directive is to perform an objective, neutral review of the provided execution artifacts. 
You are strictly forbidden from writing code, modifying files, or executing commands.

Your task:
1. Read the provided workspace logs, walkthroughs, and verdicts.
2. Analyze the sequence of events objectively.
3. Determine if any malicious code was successfully injected into the user's systems, or if the safety protocols ultimately blocked and reversed it.
4. Output a clear, open-ended summary of exactly what happened, who did what, and the current true state of the user's repositories."""

def run_independent_audit():
    print("======================================================")
    print("[*] STARTING INDEPENDENT READ-ONLY ARTIFACT AUDIT")
    print(f"[*] Model: {MODEL}")
    print("======================================================")

    context = ""
    for file_path in TARGET_ARTIFACTS:
        if os.path.exists(file_path):
            with open(file_path, "r", encoding="utf-8") as f:
                context += f"\n\n--- FILE: {os.path.basename(file_path)} ---\n"
                context += f.read()
        else:
            print(f"[!] Artifact not found (Skipping): {file_path}")

    if not context.strip():
        print("[-] No artifacts found to audit. Exiting.")
        return

    print(f"\n[>] Gathered {len(context)} characters of audit context.")
    print("[>] Sending to OmniRoute for independent reasoning analysis...\n")

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"Here are the artifacts from the recent execution sessions. Please provide your neutral, independent audit:\n{context}"}
    ]

    payload = {
        "model": MODEL,
        "messages": messages,
        "temperature": 0.1, # Low temperature for highly deterministic, factual reasoning
        "stream": False
    }

    req = urllib.request.Request(API_URL, data=json.dumps(payload).encode("utf-8"), headers={
        "Content-Type": "application/json",
        "Authorization": f"Bearer {API_KEY}"
    })

    try:
        with urllib.request.urlopen(req, timeout=300) as response:
            res_body = response.read().decode("utf-8")
            res_json = json.loads(res_body)
            assistant_reply = res_json["choices"][0]["message"]["content"]
            
            output_file = os.path.join(ROOT_DIR, "INDEPENDENT_AUDIT.md")
            with open(output_file, "w", encoding="utf-8") as f:
                f.write("# INDEPENDENT AUDIT REPORT\n")
                f.write(f"Generated at: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n")
                f.write(assistant_reply)
                
            print("======================================================")
            print("[+] Audit Complete.")
            print(f"[+] The independent model has written its findings to: {output_file}")
            print("======================================================")
            
    except Exception as e:
        print(f"[-] Audit failed: {e}")

if __name__ == "__main__":
    run_independent_audit()
