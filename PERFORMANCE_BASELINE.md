# Performance Baseline

**Date:** 2026-08-14 20:23:12
**OmniRoute:** v3.8.49 on http://localhost:20128

## Baseline Measurements

### auto/best-chat
- Min: 4.921s
- Max: 5.063s
- Avg: 4.992s
- Runs: 2

### auto/best-coding
- Min: 5.453s
- Max: 15.422s
- Avg: 10.438s
- Runs: 2

### auto/pro-coding
- Min: 10.218s
- Max: 10.218s
- Avg: 10.218s
- Runs: 1

### auto/pro-reasoning
- Min: 4.328s
- Max: 4.719s
- Avg: 4.523s
- Runs: 2

### mgmt_login
- Min: 2.704s
- Max: 3.593s
- Avg: 3.148s
- Runs: 2

### root
- Min: 6.172s
- Max: 7.329s
- Avg: 6.568s
- Runs: 3

### v1_models
- Min: 9.844s
- Max: 10.829s
- Avg: 10.386s
- Runs: 3

## Notes

- Measurements taken via localhost loopback
- Chat probes use minimal max_tokens=10
- /v1/models may include 50+ model entries
- Management API auth adds cookie/session overhead