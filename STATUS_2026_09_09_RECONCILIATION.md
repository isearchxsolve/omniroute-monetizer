# Consumer endpoint admission reconciliation

Verification: `.venv/Scripts/python.exe -m pytest -q scripts/automation/test_fleet_graduation.py` completed with **11 passed in 2.29s**. `git diff --check` passed. Updating MASTER_WORKLOG.md with apply_patch failed because its existing byte at index 29 is invalid UTF-8; this report preserves the complete entry without rewriting that existing file. The regenerated state ledger is gitignored.

### [2026-09-09] #1684 — Graduation counter corrected and inventory regenerated

The preceding recovery turn made progress by repairing the shim owner and verifying recovery. The subsequent source inspection identified a separate accounting defect: `fleet_graduation.inventory()` counted every admitted row in `admittedChatFiles`, including rows whose modality was video. The older 47-artifact ledger's 12 admissions were nine chat and three video, not 12 chat.

Changed the inventory summary to count chat and video separately and added `admittedSessionFiles` for the combined total. Updated the command output to print all three units. Added a regression fixture with one admitted chat, one admitted video, and one pending chat; it ensures pending rows do not inflate admissions and video does not inflate chat.

Regenerated the inventory using `python scripts/automation/fleet_graduation.py` without `--apply`. Result: 49 artifacts; 14 admissions comprising nine chat and five video; 28 chat artifacts require replay proof and seven video artifacts require video proof. This command performs no browser or provider request and does not alter admission records. These are historical admissions, not fresh health certifications. Two admitted Flow video rows use ChromeVideoClient and must not be described as browser-independent merely because the historical state label says PURE_PYTHON.

The video router task was independently found Disabled, last run September 2 at 13:25:55, matching the explicit emergency machine-crash containment recorded in MASTER_WORKLOG #1565. It was left disabled. Restarting the shim does not authorize undoing that separate resource-containment decision. Full browser capacity remains subject to the one-profile-at-a-time constraint.

The previous attempted multi-file Chrome safety patch failed verification and made no changes. Its proposed startup-only TCP check was insufficient to attest browser ownership or keep hot-reload readiness current; it has not been reapplied. Runtime guard coverage remains a separate unresolved issue.

The 25-chat/23-video/50-model objective remains incomplete. No admissions were fabricated, no catalog rows were truncated to manufacture 50 routes, and no video render was submitted in this increment. The corrected ledger identifies the actual missing evidence to pursue next.
