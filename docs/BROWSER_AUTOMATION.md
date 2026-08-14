# Browser / DOM Automation

## Purpose

Provider onboarding is API-first. Browser automation is a targeted fallback for
OAuth/re-auth/import/consent/manual UI flows.

## Components

- `scripts/automation/provider_browser_engine.py`
- `scripts/automation/provider_automation_orchestrator.py`

## Boundary

Automatic:
- navigation
- DOM discovery
- screenshots/HTML evidence with sanitization
- safe re-auth/refresh control detection/click

Human handoff:
- login
- password/API-key entry
- MFA/2FA/OTP
- CAPTCHA
- consent/terms
- account selection when ambiguous
- manual credential generation/import when sensitive

Never automated:
- bypassing security controls
- extraction of passwords/tokens/cookies
- service control operations against OmniRoute

## Usage

```powershell
python scripts/automation/provider_automation_orchestrator.py --provider openrouter
python scripts/automation/provider_automation_orchestrator.py --provider openrouter --reauth-probe
```

Playwright must be installed in the environment running this module.
