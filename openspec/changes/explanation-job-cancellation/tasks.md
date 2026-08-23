## 1. Session and command contract

- [x] 1.1 `[backend-dev]` Update the explanation command/session transition boundary so `cancel` is accepted only for an active explanation job, while preserving pending-export cancellation. Predecessor: none. OpenSpec: `explanation-job-cancellation`, `specs/explanation-cancellation/spec.md`. Tests: transition matrix, missing/completed session, repeated cancel.
- [x] 1.2 `[backend-dev]` Add an in-memory per-session explanation job handle with cooperative cancellation signal and one terminal-outcome claim. Predecessor: 1.1. OpenSpec: `explanation-job-cancellation`, design decision 1. Tests: registration, lookup, idempotent cancellation, no cross-thread/session cancellation. Do not add persistence.

## 2. Explanation cleanup integration

- [x] 2.1 `[backend-dev]` Connect the cancellation request to `ExplanationOrchestrator` without forcefully terminating worker threads. Predecessor: 1.2. OpenSpec: `explanation-cancellation` requirements for active jobs and command/session boundaries. Tests: cancellation before start and between segment checkpoints.
- [x] 2.2 `[backend-dev]` Add cancellation checkpoints before media preparation, before segment analysis, before publication, and before success; preserve one `finally` cleanup owner and publish-before-cleanup ordering. Predecessor: 2.1. OpenSpec: race and cleanup requirements. Tests: no fabricated/partial explanation after cancellation, cleanup exactly once, timeout/provider/publish races.
- [x] 2.3 `[backend-dev]` Add safe English cancellation/no-op responses and redacted cleanup diagnostics without media contents, transcripts, tokens, private URLs, identifiers, or unnecessary paths. Predecessor: 2.2. OpenSpec: safe response/log requirements. Tests: fixed messages and redaction assertions.

## 3. Validation and handoff

- [x] 3.1 `[backend-dev]` Run focused and full pytest suites with repository-owned/generated MP4 fixtures, compileall, `openspec validate "explanation-job-cancellation" --json`, `openspec doctor --json`, `git diff --check`, safe secret-pattern review, and FFmpeg/FFprobe smoke. Predecessor: 2.3. Report no live Slack/Anthropic QA.
- [x] 3.2 `[backend-dev]` Refresh Graphify and Codebase Memory for the exact worktree, update affected OpenSpec artifacts, document files/queries/evidence/risks, and prepare a separate PR without merging. Predecessor: 3.1. OpenSpec: `explanation-job-cancellation`.
