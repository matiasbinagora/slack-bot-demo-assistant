## Context

The Slack message handler already canonicalizes `cancel`, and the session
store already consumes cancellation for a pending export confirmation. An
explanation is different: `ExplanationOrchestrator.enqueue()` schedules a
background job, while `ExplanationOrchestrator._run()` owns the temporary
media workspace and publishes the result. There is currently no job handle,
cooperative cancellation signal, or supported explanation-cancel state.

The MVP is local-first, uses Slack Bolt Socket Mode, and validates behavior
with mocks and repository-owned/generated video fixtures. No live Slack or
Anthropic workspace is available for this change.

## Goals / Non-Goals

**Goals:**

- Define a safe `cancel` behavior while an explanation job is active.
- Keep cancellation cooperative; never kill a Python thread or leave a
  workspace without the normal cleanup boundary.
- Make cancellation idempotent and race-safe against completion, timeout,
  provider failure, and Slack publication.
- Prevent fabricated explanations, partial success claims, and sensitive
  diagnostics after cancellation.
- Preserve the existing `cancel` behavior for pending export confirmation.

**Non-Goals:**

- No export, crop, encoding, retention-policy, Slack scope, credential, or
  infrastructure changes.
- No forced interruption of an in-flight FFmpeg, FFprobe, or provider call;
  cancellation is observed at safe cooperative checkpoints.
- No live Slack or Anthropic QA.

## Decisions

### 1. Cooperative cancellation with a per-job handle

The orchestrator will register one in-memory explanation job handle per
`SessionKey`. The handle contains a cancellation event and an atomic terminal
claim. The executor remains responsible for running the job; the cancel command
only requests cancellation and does not attempt to terminate a thread.

**Alternative considered:** forcefully stopping the worker thread. Rejected
because Python cannot safely kill a thread and forced interruption could retain
media or corrupt the primary outcome.

### 2. Explicit explanation-cancel state transition

When a session is `EXPLANATION_REQUESTED` and an active job exists, `cancel`
transitions it to a terminal explanation-cancelled state and signals the job
handle. Repeated cancellation is idempotent. The existing export-pending
cancellation transition remains unchanged and is selected by the current
session state.

**Alternative considered:** reuse `CANCELLATION_CONSUMED` for both workflows.
Rejected because it would blur export confirmation semantics and make race
outcomes ambiguous.

### 3. Checkpoints and one cleanup owner

The job checks the cancellation event before media preparation, before each
segment analysis, before publishing each reply, and before declaring success.
`_run()` retains ownership of the final cleanup `finally` block. A cancellation
request never deletes media directly from the message handler.

If cancellation wins before publication, no explanation result is posted. If a
publish call has already begun or the job has atomically claimed completion,
the existing publish outcome wins; the system does not claim that already
published content was cancelled. Cleanup still executes once.

### 4. Safe user and diagnostic behavior

The user receives a short English confirmation or an already-completed/no-op
response. Logs use existing redaction utilities and contain no media contents,
transcripts, tokens, private Slack URLs, or unnecessary local paths.

### 5. Test-first contract

Tests will use fake executors, fake Slack clients, fake analyzers, controlled
temporary workspaces, and generated MP4 fixtures. They will cover state
transitions, duplicate cancellation, cancellation at each checkpoint, races
with publish/timeout/failure, cleanup idempotence, and absence of fabricated
output. Live Slack and Anthropic behavior remains explicitly unverified.

## Risks / Trade-offs

- **Cancellation arrives during a provider or FFmpeg call** → observe it at
  the next safe checkpoint and keep the existing timeout/error safeguards.
- **Cancel races with publish** → use one atomic terminal claim; the first
  terminal outcome wins and cleanup remains in `finally`.
- **In-memory job registry is lost on process restart** → keep this local-MVP
  behavior explicit; do not add persistence in this change.
- **New state can affect retry/export transitions** → add a complete transition
  matrix and preserve existing export cancellation tests.
- **A cancellation response could leak internal state** → use fixed English
  messages and redacted logging only.

## Migration Plan

1. Complete and validate the OpenSpec artifacts for this follow-up.
2. Implement behind the existing command path in a separate
   `feature/task-015-explanation-cancellation` branch.
3. Run focused/full tests, compileall, OpenSpec validation, diff and secret
   checks, and local media smoke.
4. Open a separate PR; do not merge without human approval.
5. If the change is reverted, restore the previous behavior where `cancel`
   during explanation is a safe unsupported/no-op response; export cancellation
   remains unaffected.

## Open Questions

- The exact English wording for the cancellation confirmation should be
  finalized during implementation review without exposing job identifiers or
  paths.
- The repository may later need persistent job recovery, but that is outside
  this local-first follow-up.
