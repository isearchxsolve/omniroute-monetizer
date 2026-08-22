import json
import sys
import time
from playwright.sync_api import sync_playwright
import os

# Path to the ledger
LEDGER_PATH = "d:/omniroute-monetizer/state/all_296_providers_execution_ledger.json"
WORKLOG_PATH = "d:/omniroute-monetizer/MASTER_WORKLOG.md"

def get_next_external_provider():
    """Get the next provider with EXTERNAL_ACCOUNT_REQUIRED status that hasn't been wired yet."""
    with open(LEDGER_PATH, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    for slug, provider in data['providers'].items():
        if provider.get('status') == 'EXTERNAL_ACCOUNT_REQUIRED':
            return slug, provider
    return None, None

def update_ledger(provider_slug, status, details=None):
    """Update the ledger for a provider with new status and details."""
    with open(LEDGER_PATH, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    if provider_slug in data['providers']:
        data['providers'][provider_slug]['status'] = status
        if details:
            data['providers'][provider_slug]['details'] = details
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

def main():
    # Get the next provider to process
    provider_slug, provider = get_next_external_provider()
    if not provider_slug:
        print("No more EXTERNAL_ACCOUNT_REQUIRED providers found.")
        return 0
    
    print(f"Processing provider: {provider_slug}")
    
    # Get next worklog number
    entry_number = get_next_worklog_number()
    
    # We'll use Playwright to connect to the existing Chrome instance via CDP
    try:
        with sync_playwright() as p:
            # Connect to Chrome via Chrome DevTools Protocol
            # We assume Chrome is running with remote debugging enabled on port 9222
            # If not, we will try to launch Chrome with remote debugging but using the user's profile (which may fail if profile is in use)
            try:
                # Try to connect to existing Chrome instance via CDP
                browser = p.chromium.connect_over_cdp("http://localhost:9222")
                print("Connected to existing Chrome instance via CDP")
            except Exception as e:
                print(f"Failed to connect to existing Chrome via CDP: {e}")
                # 2026-08-22 INCIDENT FIX (AGENTS.md 14.1). This fallback used to launch a
                # Playwright persistent context against the operator's LIVE Chrome profile:
                #     user_data_dir = %USERPROFILE%\AppData\Local\Google\Chrome\User Data
                # That is what revoked all four Google sessions, repeatedly. A persistent
                # context WRITES, and Google kills a session presented by a foreign browser.
                # Automation now gets its own profile and reports a login wall honestly.
                import sys as _sys
                _sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                                 "scripts", "automation"))
                from chrome_live_guard import safe_profile_dir
                user_data_dir = str(safe_profile_dir("wire_provider"))
                print(f"Using automation's own Chrome profile: {user_data_dir}")
                print("If this profile is not logged in to OmniRoute, that is a login wall -- "
                      "report it, do not open the operator's browser.")
                browser = p.chromium.launch_persistent_context(
                    user_data_dir=user_data_dir,
                    channel="chrome",
                    headless=False
                )
            
            # We assume we are already logged into OmniRoute via the existing Chrome session
            # Navigate to the OmniRoute dashboard for this provider
            page = browser.new_page()
            try:
                # Go to OmniRoute dashboard
                page.goto("http://localhost:20128/dashboard/providers")
                # Wait for the page to load
                page.wait_for_timeout(2000)
                
                # TODO: Implement the actual wiring logic for the provider
                # This is a placeholder - we need to implement the specific steps for each provider
                
                # For now, we'll just record that we started processing
                findings = f"Started processing {provider_slug}. Current status: {provider.get('status')}."
                actions_taken = f"Connected to Chrome via CDP (or launched with user data directory), navigated to OmniRoute provider dashboard."
                files_touched = "wire_provider.py (temporary script)"
                verification = "Browser connected and navigated to OmniRoute dashboard."
                status_emoji = "🔵 Info"
                
                append_worklog(
                    entry_number=entry_number,
                    title=f"Start processing {provider_slug}",
                    what=f"Begin wiring attempt for {provider_slug}",
                    why="Processing EXTERNAL_ACCOUNT_REQUIRED provider as part of the 295-provider wiring pass",
                    findings=findings,
                    actions_taken=actions_taken,
                    files_touched=files_touched,
                    verification=verification,
                    status=status_emoji
                )
                
                # Update ledger to show we started (optional)
                # update_ledger(provider_slug, "PROCESSING", {"note": "Started wiring attempt"})
                
            except Exception as e:
                findings = f"Error during processing: {str(e)}"
                actions_taken = "Exception occurred during browser automation."
                verification = f"Error: {str(e)}"
                status_emoji = "❌ Failed"
                
                append_worklog(
                    entry_number=entry_number,
                    title=f"Error processing {provider_slug}",
                    what=f"Encountered error while wiring {provider_slug}",
                    why="Error during provider wiring process",
                    findings=findings,
                    actions_taken=actions_taken,
                    files_touched="wire_provider.py",
                    verification=verification,
                    status=status_emoji
                )
            finally:
                browser.close()
    except Exception as e:
        print(f"Failed to initialize Playwright: {e}")
        return 1
    
    return 1

if __name__ == "__main__":
    sys.exit(main())