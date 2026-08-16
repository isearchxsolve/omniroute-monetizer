# Provider Adapter Policy

Provider-specific adapters must contain only evidence-backed semantics.

A provider adapter may define:
- canonical provider slug
- dashboard path
- safe control labels already observed in the Phase-A DOM evidence
- known non-secret status markers
- human-handoff conditions

Do NOT invent CSS selectors or button labels when the DOM evidence does not support them.
Run the generic discovery engine first and promote a selector only after it is observed in a real provider page.

The generic engine remains the fallback.
