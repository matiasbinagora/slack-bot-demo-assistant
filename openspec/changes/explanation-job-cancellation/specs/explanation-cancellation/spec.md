## ADDED Requirements

### Requirement: Active explanation jobs can be cancelled safely

The system SHALL accept `cancel` for a thread whose explanation job is active,
transition the explanation to a terminal cancelled state, and request
cooperative cancellation without forcefully terminating a worker thread.

#### Scenario: Cancel before the worker starts

- **WHEN** a user sends `cancel` after `explain` has been accepted but before
  the background job reaches media preparation
- **THEN** the session enters the explanation-cancelled state, the job observes
  the cancellation before doing work, no explanation is published, and any
  created workspace is cleaned up safely

#### Scenario: Cancel between segment operations

- **WHEN** a user sends `cancel` while a segmented explanation is between
  preparation, analysis, or publication checkpoints
- **THEN** the job stops at the next cooperative checkpoint, does not publish
  additional explanation content, and the complete controlled workspace is
  cleaned up exactly once

#### Scenario: Repeated cancellation

- **WHEN** a user sends `cancel` more than once for the same active explanation
  or after it has already been cancelled
- **THEN** the system returns an idempotent safe response, does not schedule a
  duplicate cleanup, and does not reopen the session

### Requirement: Cancellation races have one terminal outcome

The system SHALL resolve races between cancellation and completion, timeout,
provider failure, invalid response, or Slack publication using one atomic
terminal outcome, while preserving the existing publish-before-cleanup order.

#### Scenario: Cancellation wins before publication

- **WHEN** cancellation claims the job before any explanation reply is
  published
- **THEN** no explanation result is posted, the user receives a safe English
  cancellation response, and cleanup runs in the normal finalization boundary

#### Scenario: Publication has already started

- **WHEN** cancellation arrives after a publication attempt has started or the
  job has already claimed completion
- **THEN** the existing publication outcome wins, the system does not claim
  already-published content was cancelled, and cleanup still runs once

#### Scenario: Timeout or provider failure wins

- **WHEN** a timeout or provider/invalid-response failure claims the job before
  cancellation
- **THEN** the existing safe failure behavior is preserved, no fabricated
  explanation is posted, and cleanup runs without exposing raw diagnostics

### Requirement: Cancellation preserves command and session boundaries

The system SHALL distinguish explanation cancellation from cancellation of a
pending export confirmation and SHALL preserve existing `export` and `confirm`
transitions.

#### Scenario: Cancel an explanation session

- **WHEN** `cancel` is received while the session is in the active explanation
  state and a matching job handle exists
- **THEN** only the explanation job is cancelled and its session becomes
  terminal for that explanation request

#### Scenario: Cancel a pending export

- **WHEN** `cancel` is received while export confirmation is pending
- **THEN** the existing export cancellation transition and response remain
  unchanged

#### Scenario: Cancel without an active cancellable job

- **WHEN** `cancel` is received for a missing, completed, or otherwise
  non-cancellable explanation session
- **THEN** the system returns a safe no-op/already-completed response and does
  not mutate unrelated session state

### Requirement: Cancellation responses and logs are safe

The system SHALL use fixed English user-facing messages and redacted
diagnostics that never contain media contents, transcripts, tokens, private
Slack URLs, job identifiers, or unnecessary local paths.

#### Scenario: Cancellation confirmation

- **WHEN** an active explanation is cancelled successfully
- **THEN** the user receives a concise English confirmation without internal
  identifiers or media details

#### Scenario: Cleanup failure during cancellation

- **WHEN** cleanup fails after cancellation
- **THEN** the primary cancellation outcome remains stable, a redacted warning
  is logged, and no sensitive cleanup error details are sent to Slack

### Requirement: Cancellation behavior is tested with controlled media

The system SHALL have mocked tests and repository-owned/generated fixtures for
state transitions, cancellation checkpoints, terminal races, cleanup, and
preservation of existing export cancellation behavior.

#### Scenario: Focused cancellation test suite

- **WHEN** the focused and full Python test suites run with repository-owned
  fixtures
- **THEN** they verify cancellation before work, during segment processing,
  repeated cancellation, cancellation versus publication, timeout/provider
  races, cleanup idempotence, redaction, and unchanged export cancellation

#### Scenario: No live service claim

- **WHEN** validation is reported for this capability
- **THEN** mocked Slack/Claude and local FFmpeg/FFprobe evidence is clearly
  distinguished from live Slack or Anthropic QA
