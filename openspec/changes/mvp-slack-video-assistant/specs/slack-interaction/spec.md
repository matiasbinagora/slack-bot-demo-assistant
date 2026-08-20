## ADDED Requirements

### Requirement: Slack credentials and application configuration

The application SHALL read `SLACK_BOT_TOKEN` and `SLACK_APP_TOKEN` only from the process environment and SHALL document the required Socket Mode setup, Python 3.10+ local setup, event subscriptions, and scopes without storing credential values in the repository.

#### Scenario: Valid local configuration

- **WHEN** both required Slack tokens are present in the environment
- **THEN** the application can construct the Slack Bolt app and Socket Mode handler without reading credentials from source files

#### Scenario: Missing Slack credential

- **WHEN** a required Slack token is absent
- **THEN** startup fails with a safe configuration error that does not print the token, private URL, or other secret value

#### Scenario: Clean checkout local setup

- **WHEN** a developer starts from a clean repository checkout
- **THEN** the documented setup provides virtual environment creation plus the minimal editable and dev dependency installation commands needed to run the local Socket Mode foundation tests without live Slack credentials

### Requirement: Socket Mode lifecycle

The application SHALL expose a documented Python entrypoint that starts Slack Bolt through Socket Mode and SHALL stop cleanly when the process receives a normal termination signal.

#### Scenario: Start Socket Mode

- **WHEN** valid configuration is supplied and the local entrypoint is started
- **THEN** the process registers the configured handlers and attempts to establish the Socket Mode connection

#### Scenario: Connection failure

- **WHEN** Socket Mode cannot connect or disconnects unexpectedly
- **THEN** the process records a redacted operational error and does not report the bot as ready

### Requirement: Thread interaction and acknowledgement

The application SHALL acknowledge supported Slack events promptly, SHALL use the originating workspace/channel/thread identity for replies, and SHALL not perform FFmpeg or Claude work inside the Slack event acknowledgement callback.

#### Scenario: MP4 upload acknowledgement

- **WHEN** a `file_shared` event identifies an MP4 upload associated with a channel or thread
- **THEN** the bot acknowledges receipt in English in the relevant thread and does not generate an automatic explanation

#### Scenario: Explicit explanation request

- **WHEN** a user sends `explain` or an accepted equivalent in the video thread
- **THEN** the bot acknowledges the request and schedules the explanation outside the event callback

### Requirement: Export confirmation commands

The application SHALL recognize the canonical English thread commands `export`, `confirm`, and `cancel`, and SHALL preserve enough per-thread state to reject confirmations that do not correspond to a pending export suggestion.

#### Scenario: Export request

- **WHEN** a user sends `export` in a thread with a valid video session
- **THEN** the bot starts the export suggestion flow and records a pending confirmation for that thread

#### Scenario: Unmatched confirmation

- **WHEN** a user sends `confirm` without a pending export suggestion
- **THEN** the bot replies with a safe English explanation and does not start FFmpeg

### Requirement: Secure Slack file and message access

The application SHALL use the authenticated Slack client to retrieve file content and publish messages or uploads, SHALL treat Slack file URLs as untrusted references, and SHALL never log tokens, private URLs, raw video content, frames, or transcripts.

#### Scenario: Authenticated download

- **WHEN** media processing needs a Slack file
- **THEN** the adapter downloads it through an authenticated request into a controlled temporary path rather than passing the private URL to another component

#### Scenario: Safe message failure

- **WHEN** a Slack message or upload call fails
- **THEN** the bot records a redacted error and reports the failure without exposing credentials or private media metadata

### Requirement: Slack behavior is independently testable

The application SHALL provide a test seam for Slack Bolt event payloads and client calls so that interaction behavior can be validated without a live Slack workspace.

#### Scenario: Mocked event test

- **WHEN** a test supplies a representative `file_shared` or thread-message payload and a mocked Slack client
- **THEN** the expected acknowledgement, thread identity, state transition, and client call can be asserted without network access
