# Performance Baseline

**Date:** 2026-08-21 06:15:07
**OmniRoute:** v3.8.49 on http://localhost:20128

## Baseline Measurements

### auto/best-chat
- Min: 2.235s
- Max: 4.078s
- Avg: 3.157s
- Runs: 2

### auto/best-coding
- Min: 2.422s
- Max: 3.609s
- Avg: 3.015s
- Runs: 2

### auto/pro-coding
- Min: 3.203s
- Max: 11.407s
- Avg: 7.305s
- Runs: 2

### auto/pro-reasoning
- Min: 2.359s
- Max: 6.047s
- Avg: 4.203s
- Runs: 2

## Notes

- Measurements taken via localhost loopback
- Chat probes use minimal max_tokens=10
- /v1/models may include 50+ model entries
- Management API auth adds cookie/session overhead