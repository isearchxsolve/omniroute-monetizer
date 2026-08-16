"""Drive the crawlee-engine to run HuggingFace signup (the one-provider experiment)."""
import json
import sys
import time

sys.path.insert(0, r"C:\god_ai\api_money_bot_complete\universal_harvester")
from utils.crawlee_bridge import CrawleeBridge  # noqa: E402

with open(r"d:\omniroute-monetizer\state\hf_experiment_account.json") as f:
    acct = json.load(f)

bridge = CrawleeBridge(base_url="http://localhost:3001", timeout=300)
print("health:", bridge.health())

creds = {
    "email": acct["email"],
    "password": acct["password"],
    "username": acct["username"],
    "fullName": acct["fullName"],
}

print("firing signup for huggingface...")
t0 = time.time()
result = bridge.signup("huggingface", creds, mode="signup", options={"headless": False})
print(f"done in {time.time()-t0:.1f}s")
print(json.dumps(result, indent=2, default=str)[:3000])

with open(r"d:\omniroute-monetizer\state\hf_engine_result.json", "w") as f:
    json.dump(result, f, indent=2, default=str)
print("saved to state/hf_engine_result.json")
