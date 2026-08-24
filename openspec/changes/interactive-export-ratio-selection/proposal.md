## Why

The current Slack export flow always proposes the default `16:9` crop, even
though the media pipeline already supports additional centered-crop ratios.
Users need a clear way to select the intended output shape before confirmation
without relying on undocumented command syntax.

## What Changes

- Add a Slack `static_select` control to the export suggestion message.
- Offer `16:9`, `9:16`, `1:1`, `4:3`, and `3:4` as the only supported ratios.
- Keep `16:9` as the initial selection and preserve the existing explicit
  `confirm` and `cancel` text commands.
- Update the pending export state when the user changes the selected ratio;
  changing the selection SHALL NOT run FFmpeg or publish an output.
- Extend centered-crop geometry, output validation, fixtures, and tests for
  `4:3` and `3:4` while preserving H.264/AAC MP4 output and cleanup ordering.
- Document Slack interactivity over Socket Mode without introducing a public
  HTTP webhook or storing credentials.

## Capabilities

### New Capabilities

- None. The change extends the existing Slack interaction and video export
  capabilities.

### Modified Capabilities

- `slack-interaction`: add a testable interactive ratio selector and action
  handling for export suggestions while preserving thread identity, prompt
  acknowledgement, idempotency, and safe failures.
- `video-export`: replace the single default-only user path with a confirmed
  selection among five fixed centered-crop ratios, including `4:3` and `3:4`.

## Impact

- Affected application boundaries: Slack Bolt event/action handlers, ephemeral
  thread session state, export suggestion rendering, and media crop geometry.
- Affected validation: Slack payload/action mocks, session transition tests,
  FFmpeg/FFprobe fixture tests, publication ordering, cleanup, and live local
  Slack QA.
- Affected operational setup: Slack Interactivity must be enabled for the
  development app; Socket Mode remains the transport and no public request URL
  is introduced.
- No new runtime dependency, persistent storage, credential value, retention
  policy, or arbitrary user-supplied ratio is in scope.
