## MODIFIED Requirements

### Requirement: Export suggestion

The export flow SHALL respond to an explicit `export` request by rendering a
Slack ratio selector containing exactly `16:9`, `9:16`, `1:1`, `4:3`, and `3:4`,
with `16:9` selected by default, describing the centered crop, and asking for
confirmation in English.

#### Scenario: Export suggestion for a valid session

- **WHEN** a user sends `export` for a valid video session
- **THEN** the bot posts an English suggestion containing the default `16:9`
  ratio, a centered-crop explanation, the five approved options, and a
  confirmation request

#### Scenario: Selecting a different ratio

- **WHEN** a user selects one of `9:16`, `1:1`, `4:3`, or `3:4` while the
  suggestion is pending
- **THEN** the bot updates the pending English suggestion to show the selected
  ratio and continues to explain that the crop is centered

#### Scenario: Export request without a valid session

- **WHEN** a user sends `export` without a valid video session
- **THEN** the bot reports that an eligible video is required and does not
  invoke FFmpeg

### Requirement: Explicit confirmation gate

The export pipeline SHALL execute FFmpeg and publish no output until the same
thread has a pending suggestion with an approved selected ratio and receives an
explicit positive `confirm` command.

#### Scenario: Confirmation required

- **WHEN** a user requests export or changes the selected ratio but does not
  send `confirm`
- **THEN** no export process starts and no output file is posted

#### Scenario: Cancelled export

- **WHEN** a user sends `cancel` while an export suggestion is pending
- **THEN** the pending export is cleared, no output is generated, and the bot
  confirms cancellation in English

#### Scenario: Valid confirmation

- **WHEN** a user sends `confirm` for a pending suggestion in the same thread
- **THEN** the pipeline starts exactly one export for the currently selected
  approved ratio and marks the confirmation as consumed

### Requirement: Centered crop and output encoding

The export pipeline SHALL generate an MP4 using a centered crop to one of
`16:9`, `9:16`, `1:1`, `4:3`, or `3:4`, H.264 video, and AAC audio without
overwriting the source file.

#### Scenario: Landscape target

- **WHEN** a confirmed export selects `16:9` or `4:3` for a source with a wider
  or taller ratio
- **THEN** the output dimensions represent the selected ratio and the crop is
  centered rather than subject-tracked

#### Scenario: Portrait target

- **WHEN** a confirmed export selects `9:16` or `3:4`
- **THEN** the output dimensions represent the selected ratio and the pipeline
  uses the same centered-crop rule

#### Scenario: Square target

- **WHEN** a confirmed export selects `1:1`
- **THEN** the output dimensions are square and the pipeline uses the centered
  crop rule

### Requirement: Output validation before publication

The application SHALL validate the generated file with FFprobe before uploading
or presenting it as a successful Slack result, including the selected target
ratio among the five approved ratios.

#### Scenario: Valid encoded output

- **WHEN** FFprobe confirms an MP4 container, H.264 video, AAC audio, expected
  dimensions for the selected ratio, and a readable duration
- **THEN** the Slack adapter may publish the output in the originating thread

#### Scenario: Invalid or partial output

- **WHEN** FFprobe cannot read the file or finds an unexpected codec, container,
  dimensions, duration, or ratio
- **THEN** the output is not published and the bot reports an English export
  failure

### Requirement: Export behavior is fixture-testable

Tests SHALL use repository-owned video fixtures and mocks for Slack publication
to verify the interactive selection state, confirmation state, centered crop
dimensions for all five ratios, codecs, publication ordering, errors, and
cleanup without a live Slack workspace.

#### Scenario: End-to-end local export fixture

- **WHEN** the test suite selects each approved ratio and confirms an export
  request for repository-owned fixtures
- **THEN** FFmpeg/FFprobe assertions verify the output contract and the mocked
  Slack client receives the output only after validation
