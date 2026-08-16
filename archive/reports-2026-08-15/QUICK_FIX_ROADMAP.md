# Quick Fix Roadmap: Immediate Actions to Unblock MONETIZER

**Created:** 2026-08-15 15:55:00  
**Priority:** CRITICAL → Estimated time to recovery: **20-30 minutes**

---

## STEP-BY-STEP RECOVERY PLAN

### PHASE 1: Verify NVIDIA Account (5-10 minutes)

**1.1 Check API Key Status**
- Go to: https://integrate.api.nvidia.com/console/keys
- Look for the key corresponding to env var `NVIDIA_API_KEY`
- Check status:
  - ✅ **Green/Active** → Key is valid
  - ⚠️ **Yellow/Limited** → Rate limited or quota issues
  - ❌ **Red/Inactive** → Key is dead, proceed to 1.2

**1.2 If Key is Inactive: Generate New Key**
- Click: "+ Add API Key" button
- Name: "omniroute-monetizer-[current-date]"
- Click: Generate
- Copy the full key value (starts with `nvapi-`)
- Store safely (we'll need it in Step 2)

**1.3 Test Key Upstream (Optional)**
```bash
# In terminal, test the key with curl (if installed)
curl -X POST "https://integrate.api.nvidia.com/v1/chat/completions" \
  -H "Authorization: Bearer YOUR_NEW_KEY_HERE" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "meta/llama2-70b",
    "messages": [{"role": "user", "content": "Say OK"}],
    "max_tokens": 16
  }'
```
- If response includes content: Key is good ✅
- If response is error: Proceed to Phase 2 (contact NVIDIA support)

---

### PHASE 2: Update OmniRoute with New Key (5 minutes)

**2.1 Set Environment Variable (PowerShell)**
```powershell
$env:OMNIROUTE_PASSWORD="<REDACTED>"
$env:NVIDIA_API_KEY="nvapi-<new-key-from-step-1.2>"  # Replace with actual key

# Verify it's set
Write-Host $env:NVIDIA_API_KEY  # Should show your new key (masked for display)
```

**2.2 Inject Key into OmniRoute**
```powershell
C:/Users/Admin/AppData/Local/Programs/Python/Python311/python.exe d:\omniroute-monetizer\scripts\automation\cli_token_harvester.py
```

**Expected output:**
```
[+] Upstream VERIFIED 200 OK: nvidia (env:NVIDIA_API_KEY, nvapi-...-ULB)
[+] Injected key into nvidia connection ...
[+] nvidia post-injection test: valid=True
```

---

### PHASE 3: Test Inference Works (5 minutes)

**3.1 Test Direct Model Call**
```powershell
$env:OMNIROUTE_PASSWORD="<REDACTED>"

C:/Users/Admin/AppData/Local/Programs/Python/Python311/python.exe d:\omniroute-monetizer\scratch\test_model_direct.py
```

**Expected output:**
```json
{
  "model": "nvidia/llama-3.1-nemotron-nano-vl-8b-v1",
  "http_status": 200,
  "ok": true,
  "content_preview": "OK"
}
```

**If ok=true:** ✅ Inference works, proceed to Phase 4  
**If ok=false:** 🔴 Inference still failing, check error message and debug upstream

---

### PHASE 4: Re-run Tier 3 Optimizer (5 minutes)

```powershell
$env:OMNIROUTE_PASSWORD="<REDACTED>"

C:/Users/Admin/AppData/Local/Programs/Python/Python311/python.exe d:\omniroute-monetizer\scripts\automation\combo_optimizer.py
```

**Expected output:**
```
[+] Verified live models: 1 / 1
[+] frontier: VERIFIED OK
[+] auto/best-coding: VERIFIED OK
[+] auto/best-reasoning: VERIFIED OK
[+] auto/best-chat: VERIFIED OK
[+] auto/pro-reasoning: VERIFIED OK
[+] auto/pro-chat: VERIFIED OK
[+] Optimizer complete: 0 combo(s) changed (already optimal)
```

**All green:** ✅ MONETIZER_READY - Proceed to Phase 5

---

### PHASE 5: Final Verification (5 minutes)

**5.1 Test All Core Aliases**
```powershell
C:/Users/Admin/AppData/Local/Programs/Python/Python311/python.exe d:\omniroute-monetizer\scratch\verify_all_aliases.py
```

**Create this script first:**
```python
#!/usr/bin/env python3
import sys, json
sys.path.insert(0, 'd:\\omniroute-monetizer\\scripts\\automation')
from omniroute_api import OmniRouteAPI, save_json

api = OmniRouteAPI()
aliases = ['frontier', 'auto/best-coding', 'auto/best-reasoning', 'auto/best-chat', 
           'auto/pro-reasoning', 'auto/pro-chat', 'fusion-coder', 'kimi-coding']

results = {}
for alias in aliases:
    result = api.chat_probe(alias, timeout=30)
    results[alias] = {
        'status': result['http_status'],
        'ok': result['ok'],
        'latency': result['latency'],
    }
    status_str = "✅ OK" if result['ok'] else f"❌ FAILED ({result['http_status']})"
    print(f"{alias}: {status_str} ({result['latency']:.2f}s)")

save_json('final_verification.json', results)
all_ok = all(r['ok'] for r in results.values())
print(f"\n{'✅ ALL ALIASES WORKING' if all_ok else '❌ SOME ALIASES FAILED'}")
```

**All ✅ green:** MONETIZER IS READY

---

## ROLLBACK / FAILURE RECOVERY

**If Phase 1 fails (NVIDIA key is dead and can't regenerate):**
- Contact NVIDIA support: https://developer.nvidia.com/support
- Ask: "Why is my API key inactive?"
- Get replacement key
- Return to Phase 2

**If Phase 3 fails (Inference still failing):**
- Check error message in response
- If "rate limited": Wait 5-10 minutes, retry
- If "quota exhausted": Upgrade NVIDIA account or wait for quota reset
- If "authentication failed": Key format may be wrong, regenerate
- If "model not found": Model may have been removed, use alternative

**If Phase 4 fails (Combos still not working):**
- Check if aliases are in response but failed
- May indicate model itself is dead, not key
- Switch to openrouter (alternative provider)

---

## ALTERNATIVE: Switch to OpenRouter (Fallback)

If NVIDIA cannot be recovered quickly:

**A1. Create OpenRouter Combo**
```bash
curl -X PUT "http://localhost:20128/api/combos/openrouter-fallback" \
  -H "Authorization: Bearer AUTH_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "openrouter-fallback",
    "models": [{
      "model": "openrouter/claude-3.5-sonnet",
      "providerId": "openrouter-connection-id",
      "weight": 0
    }],
    "strategy": "priority"
  }'
```

**A2. Update Zed Config to Use Fallback**
- Edit: `%APPDATA%/Zed/settings.json`
- Change default model to `openrouter-fallback`
- Restart Zed

**A3. Declare Monetizer Ready with Fallback**
- Update STATUS.md: "MONETIZER_READY (openrouter fallback)"
- Note in report that NVIDIA recovery pending

---

## MONITORING FOR FUTURE

To prevent this from recurring:

**3.1 Add Health Check Script**
```python
#!/usr/bin/env python3
# Run every 6 hours via cron/task scheduler
import sys, json, os
sys.path.insert(0, 'd:\\omniroute-monetizer\\scripts\\automation')
from omniroute_api import OmniRouteAPI

api = OmniRouteAPI()
api.login()

# Test each provider's inference capability
health = {}
for provider in ['nvidia', 'openrouter', 'openai', 'anthropic']:
    result = api.chat_probe(provider, timeout=30)
    health[provider] = {'ok': result['ok'], 'status': result['http_status']}

# Save health report
with open('d:\\omniroute-monetizer\\state\\health_report.json', 'w') as f:
    json.dump(health, f, indent=2)

# Alert if any provider is down
if not all(h['ok'] for h in health.values()):
    print("[ALERT] Provider health check failed!")
    for p, h in health.items():
        if not h['ok']:
            print(f"  {p}: status={h['status']}")
    sys.exit(1)
```

**3.2 Add to Task Scheduler**
- Frequency: Every 6 hours
- Script: Health check script above
- Action on failure: Email administrator

---

## SUCCESS CRITERIA

Once complete, MONETIZER should satisfy:

```
✅ T1_OMNIROUTE_REACHABLE: HTTP 200 on :20128
✅ T2_V1_MODELS: HTTP 200 with model list
✅ T3_MGMT_AUTH_ENFORCED: Login required, 401 unauthenticated
✅ T4_ALIAS_FRONTIER: Returns inference result (HTTP 200, ok=true)
✅ T5_ALIAS_AUTO_PRO-CODING: Returns inference result
✅ T6_ALIAS_AUTO_PRO-REASONING: Returns inference result
✅ T7_ALIAS_AUTO_PRO-CHAT: Returns inference result
✅ T8_ZED_INTEGRATION: Configured and callable
✅ T9_NO_RESTART: OmniRoute never restarted
✅ T10_IDEMPOTENCY: No resources destroyed
✅ T11_NO_SECRETS: Secrets redacted in logs/artifacts
✅ T12_NO_NEON: Neon DB untouched
```

**Final Status:** `MONETIZER_READY` ✅

---

## ESTIMATED TOTAL TIME

| Phase | Duration | Cumulative |
| :--- | :--- | :--- |
| Phase 1: Verify NVIDIA | 5-10m | 5-10m |
| Phase 2: Inject Key | 5m | 10-15m |
| Phase 3: Test Inference | 5m | 15-20m |
| Phase 4: Run Tier 3 | 5m | 20-25m |
| Phase 5: Final Verify | 5m | 25-30m |

**Total: 25-30 minutes to MONETIZER_READY** ✅

---

## WHAT NOT TO DO

❌ **Do NOT:** Restart OmniRoute service (violates safety rule #9 from AGENTS.md)  
❌ **Do NOT:** Manually edit storage.sqlite database  
❌ **Do NOT:** Hardcode new NVIDIA key into scripts  
❌ **Do NOT:** Change combos by hand without testing  
❌ **Do NOT:** Proceed without verifying inference actually works

---

## DOCUMENTATION TO UPDATE

After successful recovery, update:
1. [STATUS.md](d:\omniroute-monetizer\STATUS.md) → "MONETIZER_READY"
2. [DEFERRED_ACTIONS.md](d:\omniroute-monetizer\DEFERRED_ACTIONS.md) → Mark as "RESOLVED"
3. [MONETIZER_FINAL_STATUS.md](d:\omniroute-monetizer\MONETIZER_FINAL_STATUS.md) → Update timestamp and test results
4. Add note to [MONETIZER_FINAL_REPORT.md](d:\omniroute-monetizer\MONETIZER_FINAL_REPORT.md) → "Updated: NVIDIA key regenerated, all tests passing"

---

**END ROADMAP**

Questions? Check [COMPREHENSIVE_ROOT_CAUSE_ANALYSIS.md](d:\omniroute-monetizer\COMPREHENSIVE_ROOT_CAUSE_ANALYSIS.md) for detailed technical breakdown.
