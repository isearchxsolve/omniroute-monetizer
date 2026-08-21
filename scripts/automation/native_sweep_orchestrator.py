import os
import json
import urllib.request
import time
from datetime import datetime

ROOT_DIR = r"D:\omniroute-monetizer"
MASTER_WORKLOG = os.path.join(ROOT_DIR, "MASTER_WORKLOG.md")
API_URL = "http://localhost:20128/v1/chat/completions"
MODEL = "frontier"
API_KEY = "sk-omniroute"

projects = [
    {
        "path": r"D:\ideation_to_prototype",
        "intent": "The executable idea is the unit of innovation. Audit this codebase to ensure it collapses the distance between thought and execution."
    },
    {
        "path": r"C:\god_ai\emergentsh",
        "intent": "Emergent.sh. Collapse the distance between thought and execution. Audit the Next.js and Docker architecture for production-ready terminal execution."
    },
    {
        "path": r"D:\god_ai\ai_video_monetizer",
        "intent": "AI Video Monetizer. Audit content generation loops and video bottlenecks blocking reality."
    },
    {
        "path": r"D:\god_ai\lasthelp\lasthelp",
        "intent": "LastHelp. Take it all the way to the terminal. Audit multi-tenant architecture to ensure the core idea is executable and not just a scaffold."
    },
    {
        "path": r"C:\god_ai\omni_server",
        "intent": "OmniRoute Monetizer Core. Audit core routing latency and token management for flawless execution."
    },
    {
        "path": r"D:\omniroute-monetizer\state\worktrees\20260819-122249-qual\neon_unified",
        "intent": "Neon Unified. Build the idea itself. Audit for strict threading locks and defensive deep-copies."
    }
]

IGNORE_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", "build", "dist", ".next"}
ALLOWED_EXTS = {".py", ".ts", ".js"} 

def collect_core_logic(target_dir):
    code_context = ""
    for root, dirs, files in os.walk(target_dir):
        dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]
        for file in files:
            if "min.js" in file or "lock" in file or ".config." in file:
                continue
            ext = os.path.splitext(file)[1].lower()
            if ext in ALLOWED_EXTS:
                path = os.path.join(root, file)
                try:
                    if os.path.getsize(path) > 15000:
                        continue
                    with open(path, "r", encoding="utf-8") as f:
                        content = f.read()
                        rel_path = os.path.relpath(path, target_dir)
                        code_context += f"--- {rel_path} ---\n{content}\n\n"
                except Exception:
                    pass
    return code_context

SYSTEM_PROMPT = """You are a Staff-Level Systems Architect and Forensic Security Auditor. 
CRITICAL DIRECTIVE - THE DUAL MANDATE:
1. Business Vision: Evaluate if this specific chunk of code fulfills the core business intent.
2. Forensic Dive: Hunt for silent failures, race conditions, memory leaks, security vulnerabilities, flawed logic, and architectural bugs.

Generate a deep-dive audit report for the provided code. DO NOT acknowledge with 'RECEIVED'. Just output the markdown report directly.
"""

def chunk_string(s, chunk_size):
    return [s[i:i+chunk_size] for i in range(0, len(s), chunk_size)] if s else []

def run():
    print("==============================================")
    print("[*] STARTING STATELESS CORE-LOGIC SWEEP (REMAINING PROJECTS)")
    print("==============================================")
    
    for p in projects:
        target_path = p["path"]
        audit_file = os.path.join(target_path, "AUDIT_REPORT.md")

        if not os.path.exists(target_path):
            print(f"[!] Skipping missing directory: {target_path}")
            continue
            
        print(f"\n[*] Processing Target: {target_path}")
        code_context = collect_core_logic(target_path)
        
        if not code_context:
            print("  [!] No valid core logic files found. Skipping.")
            continue
            
        chunks = chunk_string(code_context, 40000)
        total_chunks = len(chunks)
        print(f"  [>] Extracted Core Logic. Split into {total_chunks} stateless chunks.")
        
        with open(audit_file, "w", encoding="utf-8") as f:
            f.write(f"# STATELESS CORE LOGIC AUDIT for {target_path}\n\n")
            f.write(f"**Business Intent**: {p['intent']}\n\n")
        
        success = True
        for i, chunk in enumerate(chunks):
            chunk_num = i + 1
            user_msg = f"Audit this chunk of code ({chunk_num}/{total_chunks}) based on the business intent: {p['intent']}\n\n{chunk}"
            
            messages = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_msg}
            ]
            
            payload = {
                "model": MODEL,
                "messages": messages,
                "temperature": 0.2,
                "stream": False
            }
            
            print(f"  [>] Sending Stateless Chunk {chunk_num}/{total_chunks} ({len(user_msg)} chars)...")
            
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    time.sleep(2)
                    req = urllib.request.Request(API_URL, data=json.dumps(payload).encode("utf-8"), headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {API_KEY}"
                    })
                    with urllib.request.urlopen(req, timeout=300) as response:
                        res_body = response.read().decode("utf-8")
                        res_json = json.loads(res_body)
                        assistant_reply = res_json["choices"][0]["message"]["content"]
                        
                        with open(audit_file, "a", encoding="utf-8") as f:
                            f.write(f"\n## Audit for Chunk {chunk_num}/{total_chunks}\n")
                            f.write(assistant_reply.strip() + "\n\n")
                            
                        print(f"  [+] Wrote audit chunk {chunk_num} to disk.")
                        break
                except Exception as e:
                    print(f"  [-] Attempt {attempt+1} failed on chunk {chunk_num}: {e}")
                    if attempt == max_retries - 1:
                        success = False
                    else:
                        print("  [*] Retrying in 10s...")
                        time.sleep(10)
                        
            if not success:
                break
                
        if success:
            msg = f"Completed STATELESS Sweep on `{target_path}`. Wrote continuous audit log."
            print(f"[*] {msg}")
            with open(MASTER_WORKLOG, "a", encoding="utf-8") as f:
                f.write(f"\n### [{datetime.now().strftime('%Y-%m-%d %H:%M')}] Stateless Orchestrator\n**Status:** {msg}\n")

if __name__ == "__main__":
    run()
