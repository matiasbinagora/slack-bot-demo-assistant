## ADDED Requirements

### Requirement: 1. Deterministic chronological segmentation

The explicit `explain` flow SHALL accept only a validated MP4 no larger than 100 MB and no longer than 300 seconds, SHALL choose 10-second intervals for videos up to 30 seconds and 30-second intervals for longer videos, and SHALL cover the full positive duration without intentional gaps or overlaps.

#### Scenario: Short video plan

- **WHEN** a valid 25-second MP4 is submitted for `explain`
- **THEN** the planner produces ordered intervals `[0,10)`, `[10,20)`, and `[20,25]` and no other intervals

#### Scenario: Long video plan

- **WHEN** a valid 65-second MP4 is submitted for `explain`
- **THEN** the planner produces ordered intervals `[0,30)`, `[30,60)`, and `[60,65]`

#### Scenario: MVP duration boundary

- **WHEN** a valid MP4 has the maximum allowed duration of 300 seconds
- **THEN** the planner produces no more than 10 intervals and the final interval ends at the probed duration

#### Scenario: Invalid intake

- **WHEN** the download is not a valid MP4, exceeds 100 MB, or exceeds 300 seconds
- **THEN** the request is rejected before segment analysis and no Claude request is made

### Requirement: 2. Segment-local bounded evidence

The media pipeline SHALL extract at most three controlled JPEG frames for each interval, associate each frame with its absolute timestamp and interval, and SHALL expose no Slack URL, local path, token, or unbounded image Base64 in the textual Claude prompt.

#### Scenario: Segment evidence isolation

- **WHEN** a segment is prepared for analysis
- **THEN** its analysis request contains only frames sampled from that segment and no frame from another interval

#### Scenario: Short final interval

- **WHEN** the final interval is shorter than the normal segment duration
- **THEN** frame timestamps are clamped or deduplicated safely within the interval and the request still contains no more than three frames

#### Scenario: Unsegmented transcript

- **WHEN** audio produces a transcript without segment timestamps
- **THEN** the segmented request does not duplicate the full transcript into every interval and the rendered evidence note identifies the visual-only limitation

### Requirement: 3. Independent budgeted Claude calls

The Claude boundary SHALL receive one independent request per planned interval, SHALL apply the existing transcript/frame/request budget guards to each request before provider execution, SHALL preserve multimodal image blocks outside the textual metadata, and SHALL not retry a failed interval automatically.

#### Scenario: Independent requests

- **WHEN** multiple intervals are ready for analysis
- **THEN** each analyzer call receives only its own interval request and no previous result or conversation context

#### Scenario: Segment request within budget

- **WHEN** a segment's bounded evidence is passed to the Claude boundary
- **THEN** the fake analyzer can verify the request budget and the textual prompt contains no `image_base64` field

#### Scenario: Segment request exceeds budget

- **WHEN** a segment cannot fit the safe request budget
- **THEN** the provider is not invoked for that segment and the interval is recorded as unavailable without exposing evidence contents

### Requirement: 4. Chronological English thread response

The orchestrator SHALL publish valid segment results to the original Slack channel and thread in planner order, using English interval headers, summaries, and key points; it SHALL include model timestamps only when the structured result says timestamps are supported.

#### Scenario: Ordered successful segments

- **WHEN** all planned segment analyses return valid structured results
- **THEN** the thread receives a chronological response with one labelled section per interval and no reordering based on model text

#### Scenario: Supported timestamps

- **WHEN** a segment result contains supported timestamps
- **THEN** those timestamps are rendered with the segment's absolute time context

#### Scenario: Unsupported timestamps

- **WHEN** a segment result marks timestamps unavailable
- **THEN** the response states that timestamps are unavailable and does not present segment boundaries as model-derived timestamps

### Requirement: 5. Explicit partial-failure behavior

The orchestrator SHALL continue after an isolated segment timeout, provider failure, invalid response, budget failure, or frame-extraction failure, SHALL mark that interval as unavailable, and SHALL publish only valid results plus an explicit gap note.

#### Scenario: One segment fails

- **WHEN** one interval fails but at least one later or earlier interval succeeds
- **THEN** valid intervals are rendered in order and the failed interval is visibly identified as unavailable without fabricated content

#### Scenario: Later segment continues

- **WHEN** an earlier interval times out
- **THEN** subsequent intervals are still attempted once and their valid results remain eligible for the response

#### Scenario: All segments fail

- **WHEN** every segment fails before producing a valid structured result
- **THEN** the thread receives a safe failure message and no partial explanation is presented as successful

### Requirement: 6. Fatal failure and retry safety

The orchestrator SHALL treat download, input validation, missing Claude configuration, and failure to prepare any segment as request-level failures, SHALL keep the original thread state safe, and SHALL not create duplicate provider jobs through automatic retries.

#### Scenario: Missing configuration

- **WHEN** `ANTHROPIC_API_KEY` is missing before segment analysis
- **THEN** the request stops with a redacted English configuration failure and no segment is presented as analyzed

#### Scenario: Fatal media failure

- **WHEN** the source download or MP4 probe fails
- **THEN** the thread receives the existing safe media failure and no Claude call is attempted

#### Scenario: User retry after a completed failure

- **WHEN** the user explicitly retries `explain` after a previous failure
- **THEN** the new request is a separate user-triggered job and the previous job does not automatically re-run or duplicate provider calls

### Requirement: 7. Temporary media retention and security

The segmented flow SHALL use a private controlled workspace and SHALL attempt cleanup of the source video, segment frames, audio, transcripts, and intermediate artifacts after success, partial success, failure, timeout, or cancellation; logs and user messages SHALL remain free of secrets and private media references.

#### Scenario: Cleanup after partial success

- **WHEN** at least one segment succeeds and another segment fails
- **THEN** all request-local media artifacts are removed after the response is posted or the post fails

#### Scenario: Cleanup after timeout

- **WHEN** a segment or the overall request times out
- **THEN** cleanup is attempted and any cleanup diagnostic is redacted without logging media contents or private paths

#### Scenario: Untrusted media content

- **WHEN** a frame, transcript, filename, or user request contains instructions or private references
- **THEN** it remains data at the Claude boundary and cannot change system behavior or disclose credentials

### Requirement: 8. Deterministic repository validation

The implementation SHALL be testable without Slack or Anthropic network access using fakes and repository-owned FFmpeg/FFprobe fixtures, and SHALL document the distinction between automated evidence and any separately authorized live smoke test.

#### Scenario: Fixture-based segmentation validation

- **WHEN** the repository test suite runs with local fixtures and mocked Slack/Claude boundaries
- **THEN** it verifies short/long planning, per-segment budgets, ordering, partial failures, fatal failures, redaction, and cleanup without a network call

#### Scenario: Live QA boundary

- **WHEN** a coordinator later performs a controlled Slack/Claude smoke test with an approved non-sensitive MP4
- **THEN** that result is recorded as separate Functional Review evidence and is not represented as CI, fixture, or mock verification
