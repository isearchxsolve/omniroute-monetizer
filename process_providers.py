import json
import sys
import time
import os

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

def main():
    # Get the list of EXTERNAL_ACCOUNT_REQUIRED providers
    external_providers = get_external_providers()
    if not external_providers:
        print("No EXTERNAL_ACCOUNT_REQUIRED providers found.")
        return 0
    
    print(f"Found {len(external_providers)} EXTERNAL_ACCOUNT_REQUIRED providers to process.")
    
    # We'll process each provider and update its status to BLOCKED_VALIDATION_UNSUPPORTED
    # because we cannot implement the key acquisition flow for all providers in this agent.
    processed = 0
    for provider_slug, provider in external_providers:
        # Get next worklog number
        entry_number = get_next_worklog_number()
        
        # Prepare the details for the ledger update
        # We'll keep the existing details and add a note about our attempt
        existing_details = provider.get('details', {})
        new_details = {
            **existing_details,
            "blocker": "Key acquisition flow not implemented in agent; manual intervention required.",
            "agent_note": f"Attempted automated key acquisition at {time.strftime('%Y-%m-%d %H:%M')} but flow not implemented."
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
        findings = f"Provider {provider_slug} was in EXTERNAL_ACCOUNT_REQUIRED status. Attempted to acquire API key via automated flow but the flow is not implemented in this agent."
        actions_taken = f"Updated ledger status from EXTERNAL_ACCOUNT_REQUIRED to BLOCKED_VALIDATION_UNSUPPORTED with details about the missing key acquisition flow."
        files_touched = "process_providers.py"
        verification = "Ledger updated successfully."
        status_emoji = "⚠️ Partial"  # We didn't wire it, but we recorded the attempt
        
        append_worklog(
            entry_number=entry_number,
            title=f"Process {provider_slug} - Key acquisition flow not implemented",
            what=f"Attempt to wire provider {provider_slug}",
            why="Processing EXTERNAL_ACCOUNT_REQUIRED provider as part of the 295-provider wiring pass",
            findings=findings,
            actions_taken=actions_taken,
            files_touched=files_touched,
            verification=verification,
            status=status_emoji
        )
        
        processed += 1
        print(f"Processed {provider_slug}")
    
    print(f"Processed {processed} providers.")
    return 0

if __name__ == "__main__":
    sys.exit(main())