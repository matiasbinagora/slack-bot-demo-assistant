## Why

The MVP session model already recognizes `cancel`, but it only consumes a
pending export confirmation. An explanation runs asynchronously and has no
supported cancellation contract, so cleanup cannot claim cancellation coverage
without inventing behavior. This follow-up defines that behavior separately
from DAY-8-TASK-014 before any production implementation begins.

## What Changes

- Define an explicit user-facing cancellation command for an active explanation
  job, including its allowed session states and safe response.
- Define cancellation ownership between Slack command handling, session state,
  the background executor, and the explanation cleanup boundary.
- Ensure cancellation is idempotent, does not publish a fabricated explanation,
  and removes controlled media and derived artifacts exactly once.
- Define race behavior for cancellation versus timeout, provider failure,
  publish, retry, and a completed explanation.
- Add mocked/unit validation requirements and repository-owned media fixture
  expectations.
- Require human approval before changing the product command/state contract,
  credentials, or release status.

## Capabilities

### New Capabilities

- `explanation-cancellation`: safe cancellation of an active asynchronous video
  explanation and its temporary-media cleanup lifecycle.

### Modified Capabilities

- None. Existing explanation and Slack-interaction requirements remain the
  baseline until this change is approved and implemented.

## Impact

- Likely implementation boundaries: `session_store.py`, `slack_events.py`,
  `explanation_orchestrator.py`, executor/job coordination, and their tests.
- OpenSpec and Trello contracts will gain a separate follow-up; DAY-8-TASK-014
  remains limited to currently supported terminal states.
- No new Slack scopes, Socket Mode changes, persistence, provider changes,
  export behavior, or live Slack/Anthropic QA are included.
- Cancellation must not retain uploaded videos, frames, audio, transcripts,
  prompts, private URLs, or raw provider diagnostics.
