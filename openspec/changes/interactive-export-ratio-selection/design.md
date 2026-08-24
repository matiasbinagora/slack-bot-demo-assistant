## Context

The current export interaction accepts the text command `export`, creates an
ephemeral pending export with a fixed `16:9` suggestion, and keeps `confirm`
and `cancel` as text commands. The media pipeline already has centered-crop
support for `16:9`, `9:16`, and `1:1`, but the Slack surface does not expose a
ratio choice and the pipeline contract does not yet include `4:3` or `3:4`.

The approved interaction is a Slack Block Kit `static_select` in the export
suggestion message. It must work over Socket Mode, keep all user-facing copy
in English, and preserve the existing explicit confirmation gate and cleanup
policy.

## Goals / Non-Goals

**Goals:**

- Present a ratio selector with exactly `16:9`, `9:16`, `1:1`, `4:3`, and
  `3:4`, with `16:9` selected by default.
- Update the ephemeral pending export suggestion when a user selects a ratio,
  without downloading media, running FFmpeg, or publishing an output.
- Preserve typed `confirm` and `cancel` commands and make `confirm` consume the
  currently selected ratio.
- Extend centered crop geometry and FFprobe validation for `4:3` and `3:4`.
- Keep the behavior testable with mocked Slack action payloads and local video
  fixtures, while documenting live Slack validation separately.

**Non-Goals:**

- Arbitrary or user-entered ratios, subject tracking, smart cropping, padding,
  letterboxing, or new output containers/codecs.
- Replacing text `confirm`/`cancel` with buttons in this change.
- Automatic export, persistent sessions, permanent media storage, or a public
  HTTP webhook.
- Claude behavior, video explanation behavior, retention policy changes, or
  production deployment.

## Decisions

### 1. Use a static select menu over Socket Mode

The `export` response will include a Block Kit `static_select` whose option
values are the five fixed ratios. The bare `export` command remains compatible
and selects `16:9` initially. Slack Interactivity will be enabled for the
development app, but Socket Mode remains the transport; no request URL or new
web server is introduced.

**Alternatives considered:** accepting `export 9:16` would be smaller but is
less discoverable and conflicts with the current exact-command parser. A full
button-based workflow would unnecessarily expand the approved change because
typed `confirm` and `cancel` already work.

### 2. Keep ratio selection in the existing ephemeral session

The session store will expose a ratio-selection transition that is valid only
while an export suggestion is pending. It will preserve the file and thread
identity, replace only the pending target ratio, and reject unknown or stale
selections safely. A selection action will acknowledge promptly and update or
re-render the suggestion message; it will never invoke the export executor.

`confirm` will create the existing `ExportRequest` from the latest pending
ratio. `cancel` will clear the pending suggestion exactly as it does today.
Repeated or out-of-order actions will not create duplicate exports or reopen a
consumed confirmation.

### 3. Extend the fixed crop contract, not the input surface

The approved ratio list will become `16:9`, `9:16`, `1:1`, `4:3`, and `3:4` in
the session and media boundaries. The existing centered-crop geometry will be
reused with even dimensions and validated output metadata. H.264/AAC MP4,
FFprobe validation, validate-before-publish ordering, and cleanup remain
unchanged.

**Alternatives considered:** accepting arbitrary numeric ratios would increase
validation, UX, and media-risk surface without a product requirement. Adding
padding or subject tracking would change the crop contract and is explicitly
out of scope.

### 4. Test the action boundary independently

Tests will use representative Slack action payloads and a mocked client to
assert acknowledgement, thread resolution, menu rendering/update, session
transitions, and safe handling of invalid actions. FFmpeg/FFprobe fixture tests
will cover both new ratios and publication/cleanup ordering. No live Slack or
Anthropic claim will be derived from mocks.

## Risks / Trade-offs

- **[Slack Interactivity is not enabled or the app token is stale]** → Document
  the required app setup, require reinstall after scope/configuration changes,
  and keep action tests independent of live Slack.
- **[A stale selection races with confirm]** → Validate the session status and
  selected ratio atomically at the action/command boundary; only a pending
  session can produce an export request.
- **[Unknown action values bypass the fixed contract]** → Accept only exact
  values from the approved ratio set and return a safe English response.
- **[Odd crop dimensions produce invalid encodes]** → Preserve even-dimension
  geometry, validate codecs/dimensions with FFprobe, and test portrait and
  landscape fixtures for every added ratio.
- **[A selection accidentally starts media work]** → Assert in tests that the
  selector action performs no download, FFmpeg call, or publication.
- **[Live workspace behavior differs from mocks]** → Record live Slack QA as a
  separate validation result and never report mocked action tests as live proof.

## Migration Plan

1. Update the OpenSpec contract, session transition model, Slack Block Kit
   rendering/action handler, and media ratio geometry in one reviewed PR.
2. Enable Slack Interactivity for the authorized development app while keeping
   Socket Mode; no existing credential values are committed.
3. Run unit/integration tests, FFmpeg/FFprobe fixture checks, compile/static
   checks available in the repository, and safe secret review.
4. Run an authorized local Slack smoke test: `export`, choose each ratio,
   cancel one selection, and confirm one selection in a fresh thread.
5. Roll back by reverting the PR and disabling the interactive menu; no
   persistent data migration is required because session state is in memory.

## Open Questions

- None for the approved scope. The ratio list, select-menu interaction, typed
  confirmation/cancellation, fixed MP4 output contract, and Socket Mode
  transport are decided.
