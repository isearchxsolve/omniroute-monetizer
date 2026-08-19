import os
import subprocess
import time

projects = [
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
    }
]

env = os.environ.copy()
env['OPENAI_API_BASE'] = 'http://localhost:20128/v1'
env['OPENAI_API_KEY'] = 'sk-omniroute'

base_audit_prompt = """
You are a Staff-Level Systems Architect. Do not modify the source code files. Your task is purely analytical and test-driven.

BUSINESS INTENT CONTEXT: {intent}

DELIVERABLE CONTRACT — You must produce THREE artifacts:
1. AUDIT_REPORT.md — Brutal, honest audit covering ALL 5 gap levels:
   - LEVEL 1: Business/Vision Gap — Does the codebase achieve the stated product vision? (e.g., oiioii.ai filmmaker portfolio clone)
   - LEVEL 2: Feature Gap — Missing domain features that violate the vision (e.g., cinematic video grids, agency funnels)
   - LEVEL 3: Architectural Gap — Wrong layer boundaries, missing DI, broken hydration contracts, no separation of concerns
   - LEVEL 4: Structural Gap — Monolithic files, hidden global state, no module boundaries, circular deps
   - LEVEL 5: Defects/Bugs — Off-by-one, null derefs, race conditions, precision errors
   
2. tests/baseline/ — MODULAR, loosely-coupled failing unit/integration tests:
   - Test logical boundaries, inputs/outputs, HTTP/API contracts — NOT internal line numbers
   - Use Dependency Injection (DI) or mocked state overrides to prove no hidden global state
   - Tests must STILL PASS even if architecture is completely split/refactored
   - Each test verifies: structural issue resolved + outputs valid, without knowing physical file location
   
3. MASTER_BLUEPRINT.md — Exact, line-by-line implementation instructions to:
   - Fix all defects (Level 5)
   - Resolve structural gaps (Level 4) 
   - Fix architectural gaps (Level 3)
   - Implement missing features (Level 2)
   - Achieve business vision (Level 1)
   Mathematically precise so an execution engineer can follow it blindly.

Provide the 3 artifacts, commit them with --auto-commits, and exit.
"""

for p in projects:
    if os.path.exists(p["path"]):
        print(f"\n==============================================")
        print(f"[*] Starting Domain-Specific Deep Sweep on: {p['path']}")
        print(f"==============================================")
        
        prompt = base_audit_prompt.format(intent=p["intent"])
        
        cmd = [
            "aider", 
            "--model", "openai/agy/gemini-3.6-flash-high", 
            "--auto-commits", 
            "--yes",
            "--message", prompt
        ]
        
        try:
            subprocess.run(cmd, cwd=p["path"], env=env, check=False)
            print(f"[+] Finished sweep for {p['path']}")
        except Exception as e:
            print(f"[-] Failed sweep on {p['path']}: {e}")
        
        time.sleep(2)
    else:
        print(f"\n[!] Project missing, skipping: {p['path']}")

print("\n--- ALL DOMAIN SWEEPS INITIATED/COMPLETED ---")
