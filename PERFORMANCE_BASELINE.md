# Performance Baseline

**Date:** 2026-08-15 09:51:53
**OmniRoute:** v3.8.49 on http://localhost:20128

## Baseline Measurements

### auto/best-chat
- Min: 2.235s
- Max: 2.297s
- Avg: 2.266s
- Runs: 2

### auto/best-coding
- Min: 2.156s
- Max: 2.234s
- Avg: 2.195s
- Runs: 2

### auto/pro-reasoning
- Min: 2.156s
- Max: 2.172s
- Avg: 2.164s
- Runs: 2

### mgmt_login
- Min: 2.531s
- Max: 2.578s
- Avg: 2.554s
- Runs: 2

### root
- Min: 4.157s
- Max: 10.453s
- Avg: 6.261s
- Runs: 3

## Notes

- Measurements taken via localhost loopback
- Chat probes use minimal max_tokens=10
- /v1/models may include 50+ model entries
- Management API auth adds cookie/session overhead