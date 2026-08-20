---
name: verification-before-completion
description: Require fresh evidence before claiming a task, fix, test, build, review, or acceptance gate is complete. Use before any success or PASS statement.
---

# Verification Before Completion

No completion claim without fresh verification evidence.

1. Identify the command or observation that proves the claim.
2. Run the complete relevant command.
3. Read the full output and exit status.
4. Compare the result with the exact claim.
5. Report skipped checks, limitations, and remaining risks.

Do not treat a lint pass as proof of runtime behavior, a worker report as proof of tests, or a mocked Slack test as proof of a live Slack integration.
