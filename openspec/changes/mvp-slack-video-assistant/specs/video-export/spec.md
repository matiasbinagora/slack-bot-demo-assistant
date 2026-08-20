## ADDED Requirements

### Requirement: Export suggestion

The export flow SHALL respond to an explicit `export` request by suggesting one supported target aspect ratio from `16:9`, `9:16`, or `1:1`, describing the centered crop, and asking for confirmation in English.

#### Scenario: Export suggestion for a valid session

- **WHEN** a user sends `export` for a valid video session
- **THEN** the bot posts an English suggestion containing the selected ratio, centered-crop explanation, and a confirmation request

#### Scenario: Export request without a valid session

- **WHEN** a user sends `export` without a valid video session
- **THEN** the bot reports that an eligible video is required and does not invoke FFmpeg

### Requirement: Explicit confirmation gate

The export pipeline SHALL execute FFmpeg and publish no output until the same thread has a pending suggestion and receives an explicit positive `confirm` command.

#### Scenario: Confirmation required

- **WHEN** a user requests export but does not send `confirm`
- **THEN** no export process starts and no output file is posted

#### Scenario: Cancelled export

- **WHEN** a user sends `cancel` while an export suggestion is pending
- **THEN** the pending export is cleared, no output is generated, and the bot confirms cancellation in English

#### Scenario: Valid confirmation

- **WHEN** a user sends `confirm` for a pending suggestion in the same thread
- **THEN** the pipeline starts exactly the requested export flow and marks the confirmation as consumed

### Requirement: Centered crop and output encoding

The export pipeline SHALL generate an MP4 using a centered crop to the accepted target ratio, H.264 video, and AAC audio without overwriting the source file.

#### Scenario: Landscape target

- **WHEN** a confirmed export selects `16:9` for a source with a wider or taller ratio
- **THEN** the output dimensions represent the selected ratio and the crop is centered rather than subject-tracked

#### Scenario: Portrait or square target

- **WHEN** a confirmed export selects `9:16` or `1:1`
- **THEN** the output dimensions represent the selected ratio and the pipeline uses the same centered-crop rule

### Requirement: Output validation before publication

The application SHALL validate the generated file with FFprobe before uploading or presenting it as a successful Slack result.

#### Scenario: Valid encoded output

- **WHEN** FFprobe confirms an MP4 container, H.264 video, AAC audio, expected dimensions, and a readable duration
- **THEN** the Slack adapter may publish the output in the originating thread

#### Scenario: Invalid or partial output

- **WHEN** FFprobe cannot read the file or finds an unexpected codec, container, dimensions, or duration
- **THEN** the output is not published and the bot reports an English export failure

### Requirement: Export cleanup and failure safety

The export flow SHALL remove source copies, intermediate files, and the local output after publication or failure, and SHALL never claim success when cleanup or encoding leaves an invalid artifact.

#### Scenario: Successful publication and cleanup

- **WHEN** an encoded output passes FFprobe and is published to Slack
- **THEN** the local output and all request temporaries are deleted after publication

#### Scenario: FFmpeg failure

- **WHEN** FFmpeg exits unsuccessfully or is interrupted
- **THEN** no partial output is published, the thread receives an English error, and cleanup is attempted

### Requirement: Export behavior is fixture-testable

Tests SHALL use repository-owned video fixtures and mocks for Slack publication to verify confirmation state, crop dimensions, codecs, publication ordering, errors, and cleanup without a live Slack workspace.

#### Scenario: End-to-end local export fixture

- **WHEN** the test suite confirms an export request for a repository-owned fixture
- **THEN** FFmpeg/FFprobe assertions verify the output contract and the mocked Slack client receives the output only after validation
