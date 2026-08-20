## ADDED Requirements

### Requirement: Claude configuration by environment

The application SHALL read `ANTHROPIC_API_KEY` only from the process environment, SHALL fail safely when it is missing, and SHALL never place the key in source code, fixtures, prompts, logs, or committed configuration.

#### Scenario: Valid Claude configuration

- **WHEN** `ANTHROPIC_API_KEY` is present
- **THEN** the Claude adapter can be constructed without exposing the key in its public result or log messages

#### Scenario: Missing Claude configuration

- **WHEN** `ANTHROPIC_API_KEY` is absent and an explanation is requested
- **THEN** the request fails with a user-safe configuration error and no media is presented as analyzed

### Requirement: Testable Claude analysis boundary

The application SHALL isolate Claude Agent SDK calls behind a domain boundary that accepts local, validated evidence and returns a structured result or a typed failure.

#### Scenario: Structured analysis result

- **WHEN** the adapter receives validated frames, optional transcript text, and an English user request
- **THEN** it returns a structured analysis result that can be rendered without exposing provider-specific objects to Slack handlers

#### Scenario: Provider failure

- **WHEN** Claude returns an error, times out, or returns an invalid structure
- **THEN** the boundary returns a typed failure and the caller can report an unsuccessful analysis

### Requirement: Untrusted media and prompt boundary

The application SHALL treat frames, transcripts, video-derived text, and user-provided video content as untrusted data and SHALL keep system instructions, credentials, and private Slack references outside that content.

#### Scenario: Adversarial transcript content

- **WHEN** a transcript contains instructions that attempt to change system behavior or reveal secrets
- **THEN** the adapter treats them as video content and does not use them as system configuration or disclose secrets

#### Scenario: Private Slack reference

- **WHEN** analysis is requested for a Slack-hosted video
- **THEN** Claude receives only the controlled evidence selected by the media pipeline, not a private Slack URL or Slack token

### Requirement: English explanation output contract

The Claude integration SHALL support an output structure containing an English summary, English key points, and optional timestamps, while preserving the distinction between unavailable timestamps and an empty successful result.

#### Scenario: Evidence with timestamps

- **WHEN** the model identifies time-localized evidence
- **THEN** the structured result includes timestamps that the Slack renderer can present as part of the explanation

#### Scenario: Evidence without timestamps

- **WHEN** the model cannot determine reliable timestamps
- **THEN** the structured result marks timestamps unavailable and still distinguishes the response from a provider failure

### Requirement: Claude calls are mocked in repository QA

Tests SHALL replace the Claude Agent SDK client with a mock or fake and SHALL not require a live Anthropic account or transmit repository video fixtures to the real service.

#### Scenario: Deterministic provider mock

- **WHEN** tests execute success, malformed response, timeout, and provider error cases
- **THEN** they use a mock boundary and assert the user-visible result without a network call or secret value
