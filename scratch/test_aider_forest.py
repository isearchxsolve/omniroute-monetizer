"""Smoke-test aider against the forest (NVIDIA free key) in non-interactive mode."""
import json
import os
import subprocess
import sys
from pathlib import Path

KEYS = json.loads(Path(r"d:\omniroute-monetizer\state\forest_keys.json").read_text())
key = [k for k in KEYS["nvidia"]["keys"] if k.get("verify") == "valid"][0]["key"]

env = dict(os.environ)
env["OPENAI_API_KEY"] = key
env["OPENAI_API_BASE"] = "https://integrate.api.nvidia.com/v1"

cmd = [
    r"C:\Users\Admin\.local\bin\aider.exe",
    "--model", "openai/nvidia/nemotron-3-super-120b-a12b",
    "--weak-model", "openai/nvidia/nemotron-nano-12b-v2-vl",
    "--no-git",
    "--yes-always",
    "--no-check-update",
    "-m", "Reply with exactly one word: ready",
]
r = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=180,
                   cwd=r"d:\omniroute-monetizer\scratch")
print("exit:", r.returncode)
print("--- stdout tail ---")
print(r.stdout[-1500:])
print("--- stderr tail ---")
print(r.stderr[-500:])
