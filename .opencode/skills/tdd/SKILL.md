---
name: tdd
description: Drive test-first implementation through public behavior seams, red-green-refactor cycles, mocks, fixtures, and integration boundaries. Use when implementing or changing application behavior.
---

# Test-Driven Development

Before writing a test, identify the public seam and the behavior it proves. Prefer tests that survive internal refactors.

## Required Loop

1. State the behavior and acceptance criterion.
2. Write the smallest failing test.
3. Implement the smallest change that passes.
4. Run the focused test.
5. Refactor only after the relevant tests pass.
6. Run the broader suite before completion.

For this project, prioritize Slack event handling, idempotency, file validation, media metadata, centered crop decisions, Claude provider boundaries, cleanup, and error responses. Use mocks for Slack and Claude and deterministic video fixtures for FFmpeg behavior.
