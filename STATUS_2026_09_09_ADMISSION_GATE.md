# Admission verifier correction

### [2026-09-09] #1685 — Reject raw metadata and exception text as completion proof

Read the transfer invariants and current coordinator before attempting another admission. The prior turn was progress: the modality counter was fixed and the inventory regenerated. The next admission path calls replay_check.replay and promotes only its REPLAY_OK result, making verifier correctness a prerequisite to further graduation.

Inspection found two false-success paths. An alphabetic expected phrase in raw metadata could override an empty parsed answer. An exception whose message equals the expected numeric answer could pass classify and be returned as REPLAY_OK. Removed the raw-response promotion and explicitly prevents exception classification from returning success. Raw agent/planner markers still support the PIPELINE diagnostic classification.

Correction to the initial commentary: keyword_in_body already refused numeric expectations. Therefore the claim that a raw numeric 58 alone triggered that particular override was too broad. The verified defects are alphabetic raw-metadata promotion and exception-message promotion. No claim is made that existing admissions were produced by these defects.

Added regression tests exercising replay itself through a mocked client, with a real temporary session metadata file: empty assistant plus raw title containing the expected phrase; and RuntimeError whose message is exactly 58. Existing extracted-number success coverage remains. Ran the replay Law-3 suite and fleet coordinator suite together: 17 passed in 1.58s. No external provider request, admission mutation, browser interaction, or service restart occurred.

The existing MASTER_WORKLOG.md contains invalid UTF-8 (previous apply_patch failure at byte 29). This entry is preserved separately rather than replacing existing history. Full 25 chat / 23 video / 50-model compliance remains unproven; this fix makes the next admission decision more reliable without adding fictional seats.
