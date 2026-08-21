import os
import shutil
import subprocess
import time
import json
from datetime import datetime

# The anchor directory. We do not leave this directory.
ROOT_DIR = r"D:\omniroute-monetizer"
SIXTHRULES_SOURCE = os.path.join(ROOT_DIR, ".sixthrules")
MASTER_WORKLOG = os.path.join(ROOT_DIR, "MASTER_WORKLOG.md")

# The 12 Target Payload Projects
projects = [
    {
        "path": r"D:\omniroute-monetizer\state\worktrees\20260819-122249-qual\neon",
        "intent": "Neon Worktree (Qual). Active parallel qualification instance. Audit for state persistence and model fallback handling."
    },
    {
        "path": r"D:\omniroute-monetizer\state\worktrees\20260819-122249-qual\crypto",
        "intent": "Crypto Worktree (Qual). Active parallel qualification instance. Audit for execution timing and integration."
    },
    {
        "path": r"D:\neon_unified",
        "intent": "Neon Architect v5.1 unified package — a code-generation system. Primary issue is shared mutable class state breaking concurrent instances. Audit for these multi-instance state collisions and code-gen pipeline robustness."
    },
    {
        "path": r"C:\god_ai\oioi\oioi",
        "intent": "oiioii.ai clone (filmmaker/director portfolio). Audit must focus on domain-specific features: high-performance video grids, cinematic media loading, and agency contact funnels, alongside production backend hardening (CORS, JWT, rate-limiting on FastAPI)."
    },
    {
        "path": r"C:\god_ai\ases_v3_1",
        "intent": "ASES v3.1 — autonomous software engineering system (Planner -> Coder -> Executor -> Reviewer loop with n8n orchestrator). Audit the agent handoffs, TDD gate validations, state persistence between agents, and execution sandbox safety."
    },
    {
        "path": r"D:\ideation_to_prototype",
        "intent": "Selenium QA suite + Flask demo app. Audit for 100% test reliability, flaky Selenium selectors, Flask endpoint validation (Pydantic), and robust error handling without leaking stack traces."
    },
    {
        "path": r"C:\god_ai\emergentsh",
        "intent": "Next.js application with Docker container dependencies. Audit the Next.js build pipeline, server-side/client-side component hydration, and specifically target the Docker container build architecture for production readiness."
    },
    {
        "path": r"C:\god_ai\crypto-trader-v1_1",
        "intent": "Crypto Trader v1.1. Audit execution pipeline, trading latency, and API failover strategies."
    },
    {
        "path": r"D:\god_ai\ai_video_monetizer",
        "intent": "AI Video Monetizer. Audit content generation loops, video processing bottlenecks, and cloud storage integrations."
    },
    {
        "path": r"D:\god_ai\lasthelp\lasthelp",
        "intent": "Lasthelp. Support tooling. Audit for integration stability and query resolution accuracy."
    },
    {
        "path": r"D:\god_ai\voice_agent_avatar\voice-agent-clinic",
        "intent": "Voice Agent Clinic. Audit audio streaming latency, avatar rendering sync, and real-time inference robustness."
    },
    {
        "path": r"D:\dev\antigravity-kandover",
        "intent": "Antigravity Kandover / Godshand. Audit agent core overrides, execution sandboxing, and autonomous action loops."
    }
]

env = os.environ.copy()
env['OPENAI_API_BASE'] = 'http://localhost:20128/v1'
env['OPENAI_API_KEY'] = 'sk-omniroute'

base_audit_prompt = """
You are a Staff-Level Systems Architect (Worker 1). Your task is purely analytical and test-driven.

BUSINESS INTENT CONTEXT: {intent}

DELIVERABLE CONTRACT — You must produce THREE artifacts:
1. AUDIT_REPORT.md — Brutal, honest audit covering ALL 5 gap levels:
   - L1: Business/Vision Gap
   - L2: Feature Gap
   - L3: Architectural Gap
   - L4: Structural Gap
   - L5: Defects/Bugs
   
2. tests/baseline/ — MODULAR, loosely-coupled failing unit/integration tests
   
3. MASTER_BLUEPRINT.md — Exact, line-by-line implementation instructions

IMPORTANT RULE: You MUST log your progress and the creation of these artifacts directly to SIXTH_WORKLOG.md as per the .sixthrules file present in this directory. Do not wait until the end. Log incrementally.

CRITICAL QUALITY RULE: DO NOT output generic templates or boilerplate for your markdown artifacts. Your AUDIT_REPORT.md and MASTER_BLUEPRINT.md MUST contain highly specific code references, exact file paths, and concrete architectural findings derived from your chain-of-thought. If you find 5 defects, you must list all 5 defects with code snippets in the file.

Provide the 3 artifacts, commit them with --auto-commits, and exit.
"""

def log_to_master(message):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    entry = f"\n### [{timestamp}] Orchestrator Note\n**Status:** {message}\n"
    with open(MASTER_WORKLOG, "a", encoding="utf-8") as f:
        f.write(entry)
    print(f"[*] Logged to MASTER: {message}")

def run():
    print("==============================================")
    print("[*] STARTING ROOT-BOUND OMNI-SWEEP (ALL 12 TARGETS)")
    print("==============================================")
    
    for p in projects:
        target_path = p["path"]
        if not os.path.exists(target_path):
            print(f"\n[!] Target missing, skipping: {target_path}")
            continue
            
        print(f"\n[*] Processing Target: {target_path}")
        
        # 1. Inject .sixthrules (The Mega Prompt)
        target_rules = os.path.join(target_path, ".sixthrules")
        try:
            shutil.copy2(SIXTHRULES_SOURCE, target_rules)
            print(f"  [+] Injected .sixthrules into target.")
        except Exception as e:
            print(f"  [-] Failed to copy .sixthrules: {e}")
            continue
            
        # 2. Invoke Sweep (Worker 1)
        prompt = base_audit_prompt.format(intent=p["intent"])
        cmd = [
            "aider", 
            "--model", "openai/antigravity/gemini-3.6-flash-high", 
            "--auto-commits", 
            "--yes",
            "--message", prompt
        ]
        
        log_to_master(f"Initiated Worker 1 Sweep on `{target_path}`.")
        
        try:
            # We execute the subprocess but keep OUR process rooted in D:\omniroute-monetizer
            print(f"  [>] Launching Worker 1 Aider subprocess...")
            subprocess.run(cmd, cwd=target_path, env=env, check=False)
            print(f"  [+] Finished sweep for {target_path}")
            log_to_master(f"Completed Worker 1 Sweep on `{target_path}`.")
        except Exception as e:
            print(f"  [-] Failed sweep on {target_path}: {e}")
            log_to_master(f"FAILED Worker 1 Sweep on `{target_path}`: {e}")
        
        time.sleep(2)

if __name__ == "__main__":
    run()
