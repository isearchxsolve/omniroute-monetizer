#!/usr/bin/env python3
"""Shallow sweep: categorize remaining EXTERNAL_ACCOUNT_REQUIRED providers.

Goal: separate likely inference-API free tiers (worth trying, no card) from
GPU-cloud / training platforms (almost certainly paywalled now).
"""
import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

ledger = json.loads(open(os.path.join(ROOT, "state", "all_296_providers_execution_ledger.json"), encoding="utf-8").read())
provs = ledger["providers"]

ext = {k: v for k, v in provs.items() if v["status"] == "EXTERNAL_ACCOUNT_REQUIRED"}
print(f"EXTERNAL_ACCOUNT_REQUIRED total: {len(ext)}\n")

# Known GPU-cloud / training / paywall-prone keywords
GPU_CLOUD = {"together", "fireworks", "deepinfra", "nebius", "sambanova", "modal",
             "baseten", "replicate", "lepton", "anyscale", "hyperbolic", "novita",
             "runpod", "lambda", "coreweave", "vast", "fluidstack", "sfcompute",
             "scaleway", "ovh", "datacrunch", "jarvislabs", "latitude", "tensordock",
             "prime", "salad", "akash", "spheron", "beam", "ori", "crusoe"}

# Known inference APIs with genuine free tiers (no card)
INFER_FREE = {"groq", "gemini", "cerebras", "mistral", "cohere", "sambanova",
              "openrouter", "nvidia", "huggingface", "inference", "net", "ai21",
              "writer", "databricks", "azure", "aws", "gcp", "vertex"}

gpu_hits = []
infer_hits = []
other = []
for k in sorted(ext):
    kl = k.lower()
    if any(g in kl for g in GPU_CLOUD):
        gpu_hits.append(k)
    elif any(i in kl for i in INFER_FREE):
        infer_hits.append(k)
    else:
        other.append(k)

print("=== LIKELY GPU-CLOUD (expect paywall, low priority) ===")
for k in gpu_hits:
    print(" -", k)
print(f"   ({len(gpu_hits)})\n")

print("=== LIKELY INFERENCE-API FREE TIER (high priority, try these) ===")
for k in infer_hits:
    print(" -", k)
print(f"   ({len(infer_hits)})\n")

print("=== OTHER / UNCATEGORIZED ===")
for k in other:
    print(" -", k)
print(f"   ({len(other)})")
