## MODIFIED Requirements

### Requirement: Slack credentials and application configuration

The application SHALL read `SLACK_BOT_TOKEN` and `SLACK_APP_TOKEN` only from
the process environment and SHALL document the required Socket Mode setup,
Python 3.10+ local setup, event subscriptions, scopes, and Slack Interactivity
configuration without storing credential values in the repository.

#### Scenario: Valid local configuration

- **WHEN** both required Slack tokens are present in the environment and the
  authorized development app has Socket Mode and Interactivity enabled
- **THEN** the application can construct the Slack Bolt app and Socket Mode
  handler without reading credentials from source files

#### Scenario: Missing Slack credential

- **WHEN** a required Slack token is absent
- **THEN** startup fails with a safe configuration error that does not print the
  token, private URL, or other secret value

#### Scenario: Clean checkout local setup

- **WHEN** a developer starts from a clean repository checkout
- **THEN** the documented setup provides virtual environment creation plus the
  minimal editable and dev dependency installation commands needed to run the
  local Socket Mode foundation and interactive-action tests without live Slack
  credentials

### Requirement: Thread interaction and acknowledgement

The application SHALL acknowledge supported Slack events and interactive
actions promptly, SHALL use the originating workspace/channel/thread identity
for replies or message updates, and SHALL not perform FFmpeg or Claude work
inside the Slack acknowledgement callback.

#### Scenario: MP4 upload acknowledgement

- **WHEN** a `file_shared` event identifies an MP4 upload associated with a
  channel or thread
- **THEN** the bot acknowledges receipt in English in the relevant thread and
  does not generate an automatic explanation

#### Scenario: Explicit explanation request

- **WHEN** a user sends the canonical `explain` command in the video thread
- **THEN** the bot acknowledges the request and schedules the explanation
  outside the event callback

#### Scenario: Upload without a resolvable thread

- **WHEN** a `file_shared` event can resolve the workspace and channel but
  cannot resolve a thread for the upload
- **THEN** the bot replies in English asking the user to share the MP4 inside a
  thread, and it does not create session state or start a download

#### Scenario: Ratio selection acknowledgement

- **WHEN** a user selects an approved ratio from the pending export `static_select`
  in its originating thread
- **THEN** the action is acknowledged promptly, the pending suggestion is
  updated in that thread, and no download, FFmpeg execution, or output
  publication starts

### Requirement: Export confirmation commands

The application SHALL recognize the canonical English thread commands `export`,
`confirm`, and `cancel`, SHALL accept an interactive ratio selection only while
an export suggestion is pending, and SHALL preserve enough per-thread state to
reject confirmations that do not correspond to a pending export suggestion.

#### Scenario: Export request

- **WHEN** a user sends `export` in a thread with a valid video session
- **THEN** the bot starts the export suggestion flow, renders the approved
  ratio options with `16:9` selected by default, and records a pending
  confirmation for that thread

#### Scenario: Ratio selection before confirmation

- **WHEN** a user selects `9:16`, `1:1`, `4:3`, or `3:4` from the pending export
  selector
- **THEN** the pending export stores the selected ratio and the next `confirm`
  uses that ratio without starting media processing before confirmation

#### Scenario: Stale or invalid ratio selection

- **WHEN** an interactive action supplies an unknown ratio, targets a thread
  without a pending export, or arrives after confirmation/cancellation
- **THEN** the bot acknowledges safely, does not mutate unrelated session state,
  and does not start FFmpeg or publish an output

#### Scenario: Unmatched confirmation

- **WHEN** a user sends `confirm` without a pending export suggestion
- **THEN** the bot replies with a safe English explanation and does not start
  FFmpeg

#### Scenario: Selected confirmation

- **WHEN** a user sends `confirm` after selecting an approved ratio in the same
  thread
- **THEN** the bot creates exactly one export request for the selected ratio
  and marks the confirmation as consumed

### Requirement: Idempotent Slack event handling

The application SHALL tolerate retried Slack events, duplicate canonical
commands, and duplicate ratio-selection actions without duplicating
user-visible side effects, and SHALL ignore bot-authored thread messages.

#### Scenario: Retried upload or thread event

- **WHEN** Slack retries the same `file_shared` or canonical thread command
  event
- **THEN** the bot acknowledges the retry safely and does not duplicate replies
  or state transitions

#### Scenario: Retried ratio action

- **WHEN** Slack retries the same ratio-selection action
- **THEN** the bot does not create a second export request, duplicate a
  suggestion update, or start media processing

#### Scenario: Bot-authored message

- **WHEN** a bot-authored message is delivered through the message event
  subscription
- **THEN** the bot ignores it and does not create a loop or mutate session state

## ADDED Requirements

### Requirement: Interactive export selection is independently testable

The application SHALL provide a test seam for representative Slack Block Kit
action payloads and mocked client calls so ratio selection, thread identity,
acknowledgement, message rendering, invalid actions, and safe failures can be
validated without a live Slack workspace.

#### Scenario: Mocked ratio action test

- **WHEN** a test supplies a valid ratio-selection action payload for a pending
  export and a mocked Slack client
- **THEN** the expected acknowledgement, selected ratio transition, and
  suggestion update can be asserted without network access

#### Scenario: Mocked invalid action test

- **WHEN** a test supplies an unknown ratio or an action for a non-pending
  session
- **THEN** the mocked client receives only a safe response/update and no export
  executor call
