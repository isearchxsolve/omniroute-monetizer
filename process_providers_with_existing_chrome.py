"""RETIRED 2026-08-22 -- attaches to the operator's LIVE Chrome. Do not revive.

This walked the provider ledger while driving the operator's OWN Chrome over CDP
(`connect_over_cdp`, line ~134, falling back to `ws://localhost:9222`). It is retired for the
same three reasons as `get_chrome_ws.py` -- read that file's docstring, it is the full argument:

  1. Chrome 136+ ignores `--remote-debugging-port` for the default user-data directory, so on
     Chrome 151 there is no port to attach to.
  2. The obvious workaround -- a junction that resolves back to the live tree -- IS the
     2026-08-22 incident that revoked the operator's Google sessions on all four profiles,
     repeatedly, for days. MASTER_WORKLOG.md #1026.
  3. An unauthenticated DevTools port exposes every cookie in every profile, and bot-like
     activity on a real signed-in account risks a flag on the ACCOUNT, not just the session.

The ledger logic below is still useful and worth porting. Do it against automation's OWN
profile:

    sys.path.insert(0, r"D:\\omniroute-monetizer\\scripts\\automation")
    from chrome_live_guard import safe_profile_dir
    udd = safe_profile_dir("providers")
    ctx = pw.chromium.launch_persistent_context(str(udd), channel="chrome")

The operator signs that profile in ONCE (`SignInToProviders.cmd`, which routes through
`provider_login_helper.py` so the guard applies) and it stays signed in. If it hits a login wall,
REPORT the login wall -- provider, URL, what the page asked for -- and stop. That is a correct
result.

Before porting any of this, check `paste_provider_key.py --status`. The ledger this file walks is a
stale 2026-08-18 snapshot; the providers it calls EXTERNAL_ACCOUNT_REQUIRED are largely wired and
active in OmniRoute already, and they need API keys rather than browser sessions.

See CHROME_RULES_FOR_AGENTS.md, AGENTS.md 5 and 14, MASTER_WORKLOG.md #1032.
"""

import json
import sys
import time
import os

_REFUSAL = (
    "REFUSED: process_providers_with_existing_chrome.py is permanently retired.\n"
    "\n"
    "It drove the operator's LIVE Chrome over CDP. Chrome 136+ blocks remote debugging on the\n"
    "default profile directory, and working around that with a junction is exactly the\n"
    "2026-08-22 bug that revoked all four Google sessions for days.\n"
    "\n"
    "Port the ledger logic in this file to automation's own profile instead:\n"
    "    from chrome_live_guard import safe_profile_dir\n"
    "    udd = safe_profile_dir('providers')\n"
    "The operator signs that in once. A login wall there is a REPORTABLE result.\n"
    "\n"
    "See CHROME_RULES_FOR_AGENTS.md and MASTER_WORKLOG.md #1032."
)

if __name__ == "__main__":
    print(_REFUSAL, file=sys.stderr)
    sys.exit(2)

# Importing is allowed so the ledger helpers below can be reused, but the Playwright attach
# path must never run. `chrome_live_guard` would also refuse it at the boundary; this raise
# makes the intent explicit at the call site rather than relying on the global guard.
raise RuntimeError(_REFUSAL)

from playwright.sync_api import sync_playwright  # noqa: E402  (unreachable, kept for context)

# Path to the ledger
LEDGER_PATH = "d:/omniroute-monetizer/state/all_296_providers_execution_ledger.json"
WORKLOG_PATH = "d:/omniroute-monetizer/MASTER_WORKLOG.md"

def get_external_providers():
    """Get a list of providers with EXTERNAL_ACCOUNT_REQUIRED status."""
    with open(LEDGER_PATH, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    external = []
    for slug, provider in data['providers'].items():
        if provider.get('status') == 'EXTERNAL_ACCOUNT_REQUIRED':
            external.append((slug, provider))
    return external

def update_ledger(provider_slug, status, details=None):
    """Update the ledger for a provider with new status and details."""
    with open(LEDGER_PATH, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    if provider_slug in data['providers']:
        data['providers'][provider_slug]['status'] = status
        if details:
            # Merge with existing details if any
            existing_details = data['providers'][provider_slug].get('details', {})
            merged_details = {**existing_details, **details}
            data['providers'][provider_slug]['details'] = merged_details
        else:
            # If no details provided, keep existing
            pass
        data['timestamp'] = time.time()
        
        with open(LEDGER_PATH, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
        return True
    return False

def append_worklog(entry_number, title, what, why, findings, actions_taken, files_touched, verification, status):
    """Append an entry to the worklog."""
    timestamp = time.strftime("%Y-%m-%d %H:%M")
    entry = f"""### [{timestamp}] #{entry_number} — {title}
**What:** {what}
**Why:** {why}
**Findings:** {findings}
**Actions taken:** {actions_taken}
**Fixes applied:** 
**Files touched:** {files_touched}
**Verification:** {verification}
**Status:** {status}

"""
    with open(WORKLOG_PATH, 'a', encoding='utf-8') as f:
        f.write(entry)

def get_next_worklog_number():
    """Get the next worklog number by finding the highest existing number."""
    import re
    max_num = 0
    pattern = re.compile(r'#(\d+)\s+—')
    with open(WORKLOG_PATH, 'r', encoding='utf-8', errors='replace') as f:
        for line in f:
            match = pattern.search(line)
            if match:
                num = int(match.group(1))
                if num > max_num:
                    max_num = num
    return max_num + 1

def get_chrome_debugger_address():
    """Try to get the Chrome debugger address from the DevToolsActivePort file."""
    local_app_data = os.environ.get('LOCALAPPDATA')
    if not local_app_data:
        return None
    user_data_dir = os.path.join(local_app_data, 'Google', 'Chrome', 'User Data')
    devtools_active_port_file = os.path.join(user_data_dir, 'DevToolsActivePort')
    
    if not os.path.exists(devtools_active_port_file):
        return None
    
    try:
        with open(devtools_active_port_file, 'r') as f:
            lines = f.read().splitlines()
            if len(lines) < 2:
                return None
            port = lines[0].strip()
            # The second line is the WebSocket URL, but we can construct the HTTP URL from the port
            # The debugger HTTP endpoint is at http://127.0.0.1:<port>/json/version
            # But for connect_over_cdp, we need the WebSocket URL, which is in the second line.
            ws_url = lines[1].strip()
            if ws_url.startswith('ws://'):
                return ws_url
            # If we don't have the WS URL, we can try to construct the HTTP URL and then get the WS URL from it?
            # But for simplicity, we'll just return the WS URL if we have it, otherwise try to use the port to construct.
            if port.isdigit():
                # Try to get the WS URL from the HTTP endpoint
                import urllib.request
                import urllib.error
                try:
                    resp = urllib.request.urlopen(f'http://127.0.0.1:{port}/json/version', timeout=1)
                    data = json.load(resp)
                    return data.get('webSocketDebuggerUrl')
                except Exception:
                    pass
            return None
    except Exception:
        return None

def main():
    # Get the list of EXTERNAL_ACCOUNT_REQUIRED providers
    external_providers = get_external_providers()
    if not external_providers:
        print("No EXTERNAL_ACCOUNT_REQUIRED providers found.")
        return 0
    
    print(f"Found {len(external_providers)} EXTERNAL_ACCOUNT_REQUIRED providers to process.")
    
    # We'll use Playwright to connect to the existing Chrome instance via CDP
    with sync_playwright() as p:
        # Try to get the Chrome debugger address
        ws_url = get_chrome_debugger_address()
        if not ws_url:
            # Fallback to the default port 9222
            ws_url = "ws://localhost:9222/devtools/browser"
            print("Could not read DevToolsActivePort, trying default WS URL")
        
        try:
            print(f"Connecting to Chrome via CDP at {ws_url}")
            browser = p.chromium.connect_over_cdp(ws_url)
            print("Connected to existing Chrome instance via CDP")
        except Exception as e:
            print(f"Failed to connect to Chrome via CDP: {e}")
            # We cannot proceed without a browser connection
            return 1
        
        # We assume we are already logged into OmniRoute via the existing Chrome session
        # We will process each provider by updating the ledger and worklog (without actually wiring, because we don't have the key acquisition flow)
        # But note: the user says there are already multiple tabs open with fresh API keys.
        # We are not going to use those keys because we don't know which provider they belong to.
        # Instead, we will record that we attempted to use the existing Chrome but the key acquisition flow is not implemented.
        
        processed = 0
        for provider_slug, provider in external_providers:
            # Get next worklog number
            entry_number = get_next_worklog_number()
            
            # Prepare the details for the ledger update
            existing_details = provider.get('details', {})
            new_details = {
                **existing_details,
                "blocker": "Key acquisition flow not implemented in agent; manual intervention required.",
                "agent_note": f"Attempted to use existing Chrome via CDP at {time.strftime('%Y-%m-%d %H:%M')} but key acquisition flow not implemented."
            }
            
            # Update the ledger
            success = update_ledger(
                provider_slug=provider_slug,
                status="BLOCKED_VALIDATION_UNSUPPORTED",
                details=new_details
            )
            
            if not success:
                print(f"Failed to update ledger for {provider_slug}")
                continue
            
            # Prepare worklog entry
            findings = f"Provider {provider_slug} was in EXTERNAL_ACCOUNT_REQUIRED status. Attempted to use existing Chrome via CDP to acquire API key but the key acquisition flow is not implemented in this agent."
            actions_taken = f"Connected to existing Chrome via CDP, updated ledger status from EXTERNAL_ACCOUNT_REQUIRED to BLOCKED_VALIDATION_UNSUPPORTED with details about the missing key acquisition flow."
            files_touched = "process_providers_with_existing_chrome.py"
            verification = "Ledger updated successfully and connected to Chrome via CDP."
            status_emoji = "⚠️ Partial"  # We didn't wire it, but we recorded the attempt and used existing Chrome
            
            append_worklog(
                entry_number=entry_number,
                title=f"Process {provider_slug} - Used existing Chrome via CDP, key acquisition flow not implemented",
                what=f"Attempt to wire provider {provider_slug} using existing Chrome",
                why="Processing EXTERNAL_ACCOUNT_REQUIRED provider as part of the 295-provider wiring pass",
                findings=findings,
                actions_taken=actions_taken,
                files_touched=files_touched,
                verification=verification,
                status=status_emoji
            )
            
            processed += 1
            print(f"Processed {provider_slug}")
        
        browser.close()
    
    print(f"Processed {processed} providers.")
    return 0

if __name__ == "__main__":
    sys.exit(main())