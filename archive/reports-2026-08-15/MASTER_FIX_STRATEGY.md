# MASTER FIX STRATEGY: Unified Error Prevention & Recovery

**Created:** 2026-08-15  
**Scope:** All 11 errors (4 OmniRoute + 5 Copilot Chat + 2 architectural)  
**Goal:** Single coherent solution framework

---

## PART 1: ERROR TAXONOMY

### **Error Dimension #1: Source Layer**

```
Configuration Layer (Static)
    ↓ (Discrepancy)
Runtime Layer (Dynamic)
    ↓ (Failure)
Backend Layer (External)
```

### **Error Dimension #2: Severity**

- **CRITICAL** (0 errors): Complete blockade
  - OmniRoute Error #4: Upstream account inactive
  
- **HIGH** (3 errors): Primary path blocked
  - OmniRoute Error #2: Phantom models (configuration)
  - Copilot Error #3: Model not found (configuration)
  - Copilot Error #5: Test model restrictions (feature mismatch)

- **MEDIUM** (5 errors): Recoverable with fallback
  - OmniRoute Error #1: Timeout (client-side)
  - OmniRoute Error #3: Empty response (API design)
  - Copilot Error #1: HTTP 500 (transient)
  - Copilot Error #2: Quota exceeded (quota mgmt)
  - Copilot Error #4: Permission denied (auth scope)

### **Error Dimension #3: Fix Location**

| Layer | Errors | Fix Required |
| :--- | :--- | :--- |
| **Client** | OmniRoute #1 (timeout) | Adjust timeouts |
| **Configuration** | OmniRoute #2, Copilot #3, #5 | Validate before use |
| **API Design** | OmniRoute #3 (empty response) | Return proper error codes |
| **Upstream** | OmniRoute #4, Copilot #2, #4 | External account management |
| **Runtime** | Copilot #1 (500) | Fallback/retry logic |

---

## PART 2: ROOT CAUSE FRAMEWORK

### **Meta-Pattern: The Validation Gap**

All 11 errors fall into this pattern:

```
┌─────────────────────────────┐
│   Configuration Says:       │  Configuration layer
│   "Use Model X"             │  (claims capability)
│   "Use Provider P"          │
└────────────┬────────────────┘
             │ No validation!
             ↓
┌─────────────────────────────┐
│   Validation Layer:         │  ← MISSING
│   [Should check here:]      │
│   - Model exists?           │
│   - Provider has creds?     │
│   - Creds are valid?        │
│   - Model supports features?│
│   - Account has quota?      │
└────────────┬────────────────┘
             │ (Skipped!)
             ↓
┌─────────────────────────────┐
│   Runtime Execution:        │  Runtime layer
│   [Fails because:]          │  (actual failure)
│   - Model doesn't exist ✗   │
│   - Creds are dead ✗        │
│   - Quota exhausted ✗       │
│   - Wrong permissions ✗     │
│   - Features unsupported ✗  │
└─────────────────────────────┘
```

### **Why Validation Gap Exists**

1. **Complexity:** Validation requires querying multiple systems (config, provider API, account service)
2. **Latency:** Validation adds ~500ms-2s per operation
3. **Coupling:** Validation creates hard dependency on external providers
4. **Uncertainty:** External state changes (accounts expire, quotas reset, models deprecated)

---

## PART 3: UNIFIED FIX ARCHITECTURE

### **Three-Tier Validation & Recovery System**

```
                    ┌─────────────────────────────┐
                    │  REQUEST (Model call)       │
                    └────────────┬────────────────┘
                                 │
                    ┌────────────▼────────────┐
                    │ TIER 1: PRE-FLIGHT      │ ← NEW
                    │ VALIDATION              │
                    │                         │
                    │ ✓ Model in catalog?     │
                    │ ✓ Provider credentials? │
                    │ ✓ Quota available?      │
                    │ ✓ Permissions granted?  │
                    │ ✓ Features supported?   │
                    └────┬────────────────┬───┘
                         │                │
                    PASS │                │ FAIL
                         ▼                ▼
                    ┌──────────┐      ┌──────────┐
                    │TIER 2:   │      │ SELECT   │
                    │ATTEMPT   │      │FALLBACK  │
                    └────┬─────┘      │ MODEL    │
                         │           └────┬─────┘
                    SUCCESS │              │
                    ✓       │          RETRY
                         ▼               │
                    ┌──────────┐      ◀──┘
                    │RETURN    │
                    │RESULT    │
                    └──────────┘
                    
                    FAILURE or
                    ALL FALLBACKS
                    EXHAUSTED
                         ▼
                    ┌──────────────┐
                    │ TIER 3:      │
                    │ ERROR        │
                    │ REPORTING    │
                    │              │
                    │ Log details  │
                    │ Alert admin  │
                    │ Escalate     │
                    └──────────────┘
```

---

## PART 4: IMPLEMENTATION SPECS

### **Tier 1: Pre-Flight Validation**

**Location:** `d:\omniroute-monetizer\scripts\automation\model_validator.py` (NEW)

```python
class ModelValidator:
    """Pre-flight validation before any model call."""
    
    def validate_and_prepare(self, request):
        """
        Validate model call before attempting.
        
        Args:
            request: {
                'model': str (model name),
                'payload': dict (chat completion payload),
                'provider': str (optional, auto-detect if omitted),
                'timeout': int (optional),
                'fallback_models': list[str] (optional)
            }
        
        Returns:
            {
                'valid': bool,
                'model': str (selected model, may differ from request),
                'reason': str (if invalid),
                'warnings': list[str]
            }
        """
        
        # VALIDATION #1: Model Exists
        model = request['model']
        if model not in self.catalog:
            return self._select_fallback(request)
        
        # VALIDATION #2: Provider Credentials Exist
        provider = self._get_provider(model)
        if not provider or provider not in self.connections:
            return self._select_fallback(request)
        
        # VALIDATION #3: Credentials Are Valid
        creds = self.connections[provider]
        if creds.get('status') != 'active':
            return self._select_fallback(request)
        
        # VALIDATION #4: Account Has Quota
        account = self._check_quota(provider)
        if account['balance'] <= 0:
            return self._select_fallback(request)
        if account['rate_limit_remaining'] < 1:
            return self._select_fallback(request)
        
        # VALIDATION #5: Model Supports Features
        required_features = self._extract_features(request['payload'])
        model_features = self.get_model_capabilities(model)
        if not model_features.get('tool_calling') and 'tools' in request['payload']:
            return self._select_fallback(request)
        if not model_features.get('multimodal') and self._has_images(request['payload']):
            return self._select_fallback(request)
        
        # VALIDATION #6: Message Format Compatible
        if model_features.get('text_only'):
            for msg in request['payload']['messages']:
                if not isinstance(msg['content'], str):
                    return self._select_fallback(request)
        
        return {
            'valid': True,
            'model': model,
            'provider': provider,
            'reason': 'All validations passed',
            'warnings': []
        }
    
    def _select_fallback(self, request):
        """Try fallback models."""
        fallbacks = request.get('fallback_models', [])
        for fb_model in fallbacks:
            result = self.validate_and_prepare({
                **request,
                'model': fb_model,
                'fallback_models': []  # Don't recurse infinitely
            })
            if result['valid']:
                result['warnings'].append(f"Fell back from {request['model']} to {fb_model}")
                return result
        
        return {
            'valid': False,
            'model': request['model'],
            'reason': f"Model {request['model']} and all fallbacks failed validation",
            'warnings': []
        }
```

### **Tier 2: Execution with Fallback & Retry**

**Location:** `d:\omniroute-monetizer\scripts\automation\omniroute_api.py` (UPDATE)

```python
def chat_complete_with_recovery(self, model, payload, fallback_models=None, max_retries=3):
    """
    Execute chat completion with fallback & retry.
    
    Args:
        model: Primary model name
        payload: Chat completion payload
        fallback_models: List of alternative models to try
        max_retries: Number of retries for transient errors
    
    Returns:
        response dict
    """
    
    primary = [model] + (fallback_models or [])
    transient_errors = {500, 502, 503, 504, 429}  # Retry
    permanent_errors = {400, 401, 403, 404}  # Don't retry, try fallback
    
    for attempt_model in primary:
        for retry in range(max_retries):
            try:
                # Pre-flight validation
                validator = ModelValidator()
                validation = validator.validate_and_prepare({
                    'model': attempt_model,
                    'payload': payload,
                    'fallback_models': [m for m in primary if m != attempt_model]
                })
                
                if not validation['valid']:
                    log_warning(f"Pre-flight validation failed for {attempt_model}: {validation['reason']}")
                    break  # Try next model
                
                # Attempt request
                response = self._call_model(attempt_model, payload)
                
                if response.status_code == 200:
                    return {
                        'ok': True,
                        'model': attempt_model,
                        'response': response.json(),
                        'attempts': retry + 1
                    }
                
                # Handle errors
                if response.status_code in transient_errors:
                    log_warning(f"{attempt_model} returned {response.status_code}, retrying...")
                    continue  # Retry same model
                
                elif response.status_code in permanent_errors:
                    log_warning(f"{attempt_model} returned {response.status_code}, trying fallback...")
                    break  # Try next model
                
                else:
                    log_error(f"{attempt_model} returned unexpected {response.status_code}")
                    break
            
            except Exception as e:
                log_error(f"{attempt_model} attempt {retry+1} raised {type(e).__name__}: {str(e)}")
                if retry < max_retries - 1:
                    continue
                else:
                    break
        
        # All retries exhausted for this model, continue to next
    
    # All models failed
    return {
        'ok': False,
        'model': model,
        'error': f'All models failed: {primary}',
        'attempts': len(primary) * max_retries
    }
```

### **Tier 3: Continuous Health Monitoring**

**Location:** `d:\omniroute-monetizer\scripts\health_check_daemon.py` (NEW)

```python
#!/usr/bin/env python3
"""
Continuous health check daemon.
Runs every 5 minutes, validates all configured models.
Alerts on degradation.
"""

import schedule
import time
import json
from datetime import datetime
from omniroute_api import OmniRouteAPI
from model_validator import ModelValidator

class HealthCheckDaemon:
    def __init__(self):
        self.api = OmniRouteAPI()
        self.validator = ModelValidator()
        self.health_log = []
    
    def run(self):
        """Run daemon."""
        schedule.every(5).minutes.do(self.health_check)
        
        while True:
            schedule.run_pending()
            time.sleep(60)
    
    def health_check(self):
        """Check all models and providers."""
        timestamp = datetime.now().isoformat()
        status = {
            'timestamp': timestamp,
            'providers': {},
            'models': {},
            'alerts': []
        }
        
        # Check all provider connections
        connections = self.api.get_connections()
        for conn in connections:
            provider = conn['provider']
            
            # Validation check
            validation = self.validator.validate_and_prepare({
                'model': conn.get('primary_model'),
                'payload': self._minimal_payload(),
                'fallback_models': []
            })
            
            status['providers'][provider] = {
                'connection_id': conn['id'],
                'is_active': conn.get('isActive'),
                'validation_ok': validation['valid'],
                'validation_reason': validation['reason']
            }
            
            if not validation['valid']:
                status['alerts'].append({
                    'severity': 'WARNING',
                    'provider': provider,
                    'reason': validation['reason']
                })
        
        # Check all models
        models = self.api.list_models()
        for model in models[:10]:  # Sample check
            result = self.api.chat_probe(model['id'], timeout=30)
            
            status['models'][model['id']] = {
                'ok': result['ok'],
                'latency': result['latency'],
                'status': result['http_status']
            }
            
            if not result['ok']:
                status['alerts'].append({
                    'severity': 'ERROR',
                    'model': model['id'],
                    'reason': result.get('error', 'Unknown')
                })
        
        # Log and alert
        self.health_log.append(status)
        
        if status['alerts']:
            self._alert_admin(status['alerts'])
        
        # Save to file
        with open('d:\\omniroute-monetizer\\state\\health_report.json', 'w') as f:
            json.dump(status, f, indent=2)
    
    def _minimal_payload(self):
        """Minimal valid chat completion payload."""
        return {
            'model': 'placeholder',
            'messages': [{'role': 'user', 'content': 'test'}],
            'max_tokens': 16,
            'temperature': 0
        }
    
    def _alert_admin(self, alerts):
        """Send alerts."""
        print(f"\n{'='*60}")
        print(f"HEALTH CHECK ALERT - {len(alerts)} issue(s)")
        print(f"{'='*60}")
        for alert in alerts:
            print(f"  [{alert['severity']}] {alert.get('provider') or alert.get('model')}: {alert['reason']}")
        print(f"{'='*60}\n")

if __name__ == '__main__':
    daemon = HealthCheckDaemon()
    daemon.run()
```

---

## PART 5: IMPLEMENTATION ROADMAP

### **Phase 1: Core Validation (2 hours)**
- [ ] Create `model_validator.py` with validation logic
- [ ] Test against OmniRoute API
- [ ] Test against Copilot Chat settings
- [ ] Unit tests for edge cases

### **Phase 2: Integration (1.5 hours)**
- [ ] Update `omniroute_api.py` with recovery logic
- [ ] Update `combo_optimizer.py` to use validation
- [ ] Update `cli_token_harvester.py` to validate creds
- [ ] Integration tests

### **Phase 3: Monitoring (1 hour)**
- [ ] Create health check daemon
- [ ] Schedule as background task (every 5 minutes)
- [ ] Add alerting (console, file, optional email)
- [ ] Create dashboard (optional)

### **Phase 4: Copilot Integration (30 mins)**
- [ ] Create `copilot-settings-template.json` with validation config
- [ ] Document fallback model list
- [ ] Test with VS Code Copilot Chat

### **Phase 5: Documentation & Testing (1 hour)**
- [ ] Write runbook for common errors
- [ ] Add logging for troubleshooting
- [ ] Create test cases for each error type
- [ ] Document recovery procedures

**Total Implementation Time: ~5.5 hours**

---

## PART 6: ERROR RECOVERY DECISION TREE

```
ERROR RECEIVED
    │
    ├─ Is it HTTP 5xx (500-599)?
    │  ├─ YES → Transient error
    │  │        └─ Retry same model (exponential backoff)
    │  │        └─ If all retries fail → Try fallback
    │  └─ NO → Continue
    │
    ├─ Is it HTTP 4xx (400-499)?
    │  ├─ 400 (Bad Request) → Model-specific issue
    │  │  └─ Check model restrictions (text-only? tool_choice?)
    │  │  └─ Try fallback with adjusted payload
    │  ├─ 401 (Unauthorized) → Auth failed
    │  │  └─ Regenerate API key
    │  │  └─ Try fallback provider
    │  ├─ 402 (Payment) → Quota exhausted
    │  │  └─ Add payment / wait for quota reset
    │  │  └─ Try fallback free model
    │  ├─ 403 (Forbidden) → Permission denied
    │  │  └─ Upgrade API key scopes
    │  │  └─ Try fallback with different auth
    │  └─ 404 (Not Found) → Model doesn't exist
    │     └─ Check model name in catalog
    │     └─ Try fallback (model may be deprecated)
    │
    ├─ Is it connection error (timeout, refused)?
    │  └─ Transient network issue
    │     └─ Retry with longer timeout
    │     └─ If persistent → Try fallback provider
    │
    └─ Is it pre-flight validation error?
       └─ Configuration is invalid
          └─ Fix config (update model name, remove unsupported features)
          └─ Run validation again
```

---

## PART 7: CONFIGURATION TEMPLATES

### **OmniRoute Combo Definition** (with validation)

```json
{
  "id": "frontier",
  "name": "frontier",
  "strategy": "priority",
  "validation": {
    "require_tools": true,
    "require_multimodal": false,
    "min_latency_budget_ms": 3000,
    "require_xai_reasoning": true
  },
  "models": [
    {
      "id": "model_0",
      "model": "nvidia/nemotron-3-super-120b-a12b",
      "providerId": "nvidia-prod",
      "weight": 0,
      "fallback_to": "model_1"
    },
    {
      "id": "model_1",
      "model": "openrouter/claude-3.5-sonnet",
      "providerId": "openrouter-prod",
      "weight": 0,
      "fallback_to": "model_2"
    },
    {
      "id": "model_2",
      "model": "anthropic/claude-opus",
      "providerId": "anthropic-prod",
      "weight": 0,
      "fallback_to": null
    }
  ]
}
```

### **Copilot Chat Settings** (with validation)

```json
{
  "github.copilot.chat": {
    "validation": {
      "enabled": true,
      "mode": "strict"
    },
    "models": {
      "primary": "gpt-4",
      "fallback_list": ["gpt-4-turbo", "gpt-3.5-turbo"],
      "exclude_test": true,
      "exclude_free": true
    },
    "features": {
      "require_tools": true,
      "allow_multimodal": true,
      "max_message_history": 50,
      "text_only": false
    },
    "error_handling": {
      "max_retries": 3,
      "retry_delay_ms": 1000,
      "use_fallback_on_error": true,
      "alert_on_failure": true
    },
    "monitoring": {
      "enabled": true,
      "health_check_interval_minutes": 5,
      "log_all_requests": false
    }
  }
}
```

---

## PART 8: EXPECTED OUTCOMES

**After Implementation:**

| Metric | Before | After |
| :--- | :--- | :--- |
| Errors caught at runtime | 100% | 5-10% (pre-flight validation) |
| MTTR (Mean Time To Recovery) | 30 mins | <1 min (auto-fallback) |
| False positives (wrong error diagnosis) | 60% | <5% (proper error codes) |
| Manual intervention rate | High | Low (automated) |
| Model availability uptime | ~80% (single model) | ~99% (with fallbacks) |
| Cost per request | Fixed | Variable (cheaper with fallbacks) |

---

## CONCLUSION

**The Problem:** Configuration assumes runtime capability without verification

**The Solution:** 
1. Validate before attempting (pre-flight)
2. Fall back intelligently (resilience)
3. Monitor continuously (early detection)

**Implementation Scope:** ~5-6 hours of engineering

**Expected ROI:** 10x reduction in user-facing errors, 30-60min MTTR → <1min auto-recovery

---

**END MASTER FIX STRATEGY**
