---
name: slack-bot-builder
description: Build and review the Python Slack Bolt application, including Socket Mode events, file uploads, thread replies, scopes, acknowledgements, and testable handlers. Use when implementing or reviewing Slack bot behavior.
---

# Slack Bot Builder

Use Python Slack Bolt with Socket Mode for the MVP.

## Implementation Rules

- Acknowledge Slack events within the platform deadline and hand long video work to a background job or worker boundary.
- Validate event type, channel/thread context, file metadata, MIME type, size, and duration before downloading.
- Download Slack files only with the bot token and authorized URLs. Do not trust user-provided URLs.
- Reply in the originating thread and keep user-facing text in English.
- Request the minimum Slack scopes needed for reading files, receiving events, posting thread replies, and uploading outputs.
- Keep Slack handlers thin; put media and model work behind testable application services.
- Make duplicate event handling idempotent.
- Return actionable error messages without exposing tokens, local paths, prompts, or provider internals.

## Testing

Use mocked Slack payloads and deterministic fixtures for file events, duplicate events, unauthorized files, size limits, failed downloads, and thread replies. A test is not proof of a live workspace integration unless it actually runs against Slack.
