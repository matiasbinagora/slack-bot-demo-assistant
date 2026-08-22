## ADDED Requirements

### Requirement: MP4 intake limits

The media pipeline SHALL accept only valid MP4 input with a maximum size of 100 MB and a maximum duration of 300 seconds, and SHALL enforce the byte limit while downloading rather than trusting metadata alone.

#### Scenario: Valid MP4

- **WHEN** an authenticated Slack download is an MP4 no larger than 100 MB and no longer than 300 seconds
- **THEN** the pipeline accepts it for an explicit explanation request

#### Scenario: Invalid format

- **WHEN** a file is not a valid MP4 according to content/container validation
- **THEN** the pipeline rejects it before Claude or expensive media processing runs

#### Scenario: Size or duration limit exceeded

- **WHEN** the download exceeds 100 MB or FFprobe reports a duration greater than 300 seconds
- **THEN** the pipeline rejects the request, reports a clear English error, and does not continue analysis

### Requirement: Safe temporary media workspace

The pipeline SHALL create a private, controlled temporary workspace per request and SHALL prevent path traversal, arbitrary output paths, and accidental reuse of another request's media.

#### Scenario: Controlled input path

- **WHEN** a video is downloaded for processing
- **THEN** its path is generated under the configured temporary root and is not derived directly from an untrusted Slack filename

#### Scenario: Cleanup after failure

- **WHEN** validation, extraction, transcription, or analysis fails
- **THEN** the request workspace is removed or securely scheduled for removal and no partial artifact is retained as a successful result

### Requirement: Explicit explanation processing

The pipeline SHALL process video understanding only after an explicit user request from the associated thread and SHALL use selected frames plus optional audio/transcript evidence to produce the Claude input.

#### Scenario: No automatic explanation

- **WHEN** a valid MP4 is uploaded but the user has not asked for an explanation
- **THEN** the bot acknowledges the upload without invoking Claude or presenting a summary

#### Scenario: Explanation request

- **WHEN** the user sends `explain` or an accepted equivalent for a valid video session
- **THEN** the pipeline extracts bounded configured evidence, passes frame images through the approved multimodal Claude boundary only when the request stays within the safe budget, and renders the resulting English explanation in the same thread

### Requirement: Explanation result and failure behavior

The pipeline SHALL return an English summary and key points, SHALL include timestamps only when they are supported by evidence, and SHALL expose media/provider failures as failures rather than fabricated explanations.

#### Scenario: Successful explanation

- **WHEN** evidence analysis completes with a valid structured Claude result
- **THEN** the thread receives an English summary, English key points, and available timestamps

#### Scenario: Unavailable evidence

- **WHEN** audio, transcription, or timestamps are unavailable but visual analysis can continue
- **THEN** the response identifies the unavailable evidence without claiming unsupported timestamps and completes only if the remaining result is valid

#### Scenario: Processing failure

- **WHEN** FFmpeg, FFprobe, transcription, Claude, or cleanup encounters a fatal error
- **THEN** the thread receives a clear English failure message and no unverified summary is published

### Requirement: Media retention minimization

The pipeline SHALL delete downloaded videos, extracted frames, transcripts, intermediate audio, and local analysis artifacts after each request completes, fails, or is cancelled.

#### Scenario: Successful cleanup

- **WHEN** a valid explanation has been rendered in Slack
- **THEN** all local source and derived media for that request are deleted while the thread message remains the only user-facing record produced by the app

#### Scenario: Cleanup is attempted after every terminal state

- **WHEN** a request exits through success, validation failure, provider failure, cancellation, or timeout
- **THEN** cleanup is attempted and any cleanup failure is recorded as an operational risk without logging media contents

### Requirement: Video understanding uses repository fixtures

The implementation SHALL provide tests that exercise valid, invalid, oversized, over-duration, provider-failure, and cleanup paths with repository-owned fixtures and mocks.

#### Scenario: Fixture-based validation

- **WHEN** the test suite runs without Slack, Claude, or external media access
- **THEN** it validates intake, extraction boundaries, rendering, errors, and retention behavior deterministically
