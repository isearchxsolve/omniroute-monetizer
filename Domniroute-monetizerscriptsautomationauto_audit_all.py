import os
import subprocess
import time

projects = [
    r'D:\neon_unified',
    r'C:\god_ai\oioi\oioi',
    r'C:\god_ai\ases_v3_1',
    r'D:\ideation_to_prototype',
    r'C:\god_ai\emergentsh'
]

env = os.environ.copy()
env['OPENAI_API_BASE'] = 'http://localhost:20128/v1'
env['OPENAI_API_KEY'] = 'sk-omniroute'

audit_prompt = """You are a Staff-Level Systems Architect. Read the entire repository. 
1. Create a file named 'AUDIT_REPORT.md' detailing critical structural flaws, missing features, concurrency risks, and security vulnerabilities.
2. Create a folder 'tests/baseline/'.
3. Write failing unit/integration tests in this folder that expose the flaws found in your audit.
4. Create a comprehensive file 'MASTER_BLUEPRINT.md' that gives exact, line-by-line instructions to fix the bugs and pass the tests.
Do NOT modify the source code files. Give me the audit, the tests, and the blueprint.
"""

for p in projects:
    if os.path.exists(p):
        print(f"\n==============================================")
        print(f"[*] Starting Deep Sweep on: {p}")
        print(f"==============================================")
        
        cmd = [
            "aider", 
            "--model", "openai/agy/gemini-3.6-flash-high", 
            "--auto-commits", 
            "--yes",
            "--message", audit_prompt
        ]
        
        try:
            # We use Popen so we can stream output
            proc = subprocess.Popen(cmd, cwd=p, env=env, shell=True)
            proc.wait()
            print(f"[+] Finished sweep for {p}")
        except Exception as e:
            print(f"[-] Failed sweep on {p}: {e}")
        
        time.sleep(2)
        
