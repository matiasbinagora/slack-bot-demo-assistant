# Slack Video Assistant

Local-first Slack bot for understanding and exporting short videos.

## Status

This repository currently contains the OpenCode and Orca agent bootstrap, project governance rules, and the initial product contract. The Slack application is not implemented yet.

## Product Goal

The bot will let a user upload an MP4 video to Slack and interact with it in English:

1. Upload a video and continue in the Slack thread.
2. Ask what the video is about.
3. Receive an English summary with key points and timestamps when available.
4. Request an export format or aspect ratio.
5. Receive a suggested format and centered crop for confirmation.
6. Receive an H.264/AAC MP4 export after confirmation.

Temporary videos, frames, transcripts, and generated outputs are deleted after processing.

## MVP Contract

- Language: Python.
- Slack framework: Slack Bolt.
- Slack connection: Socket Mode.
- Claude integration: Claude Agent SDK.
- User-facing language: English.
- Input: MP4, up to 100 MB and 5 minutes.
- Output: MP4 with H.264 video and AAC audio.
- Crop strategy: suggest an aspect ratio and use a centered crop after confirmation.
- Test strategy: mocks and repository-owned video fixtures.
- Deployment: local development first.

## Agent Workflow

```text
User request
    |
    v
orca (primary)
    |
    +-- scope, OpenSpec, governance, Trello
    +-- Orca Run / Task / Dispatch
    |
    v
backend-dev (subagent)
    |
    +-- Python, Slack Bolt, Claude Agent SDK
    +-- FFmpeg, fixtures, tests
    +-- branch and pull request
    |
    v
orca review gates
    |
    +-- Code Review
    +-- Functional Review
    +-- QA evidence and user approval
```

`orca` can create or update Trello cards and comment on GitHub pull requests. It must request human approval before merging a PR, closing a card, changing credentials, or expanding the approved scope.

## Repository Agents

### `orca`

The primary repository agent. It owns scope definition, product governance, OpenSpec planning, Trello card quality, developer handoffs, PR review coordination, and final QA decisions. It must use the real Orca runtime for supervised dispatches and must not write production code.

### `backend-dev`

The implementation subagent. It owns the Python Slack bot, Claude integration, video pipeline, tests, fixtures, branch, and PR. It works only from a complete handoff and must provide fresh validation evidence.

## Local Setup

Copy `.env.example` to a local environment file and provide values without committing secrets:

```text
ANTHROPIC_API_KEY=
SLACK_BOT_TOKEN=
SLACK_APP_TOKEN=
MAX_VIDEO_BYTES=104857600
MAX_VIDEO_DURATION_SECONDS=300
VIDEO_TEMP_DIR=
LOG_LEVEL=INFO
```

The Trello and GitHub MCP gateways use the ignored `.env.mcp` file. Each worktree needs its own local credentials file before mutating Trello or GitHub.

Required media tooling for the planned local pipeline:

- Python 3
- FFmpeg
- FFprobe
- Whisper only if local audio transcription is enabled

## Quality Gates

Every implementation task must have:

- A Trello card or an explicit OpenSpec exception.
- Numbered acceptance criteria.
- Unit or integration tests at agreed public seams.
- FFmpeg and video fixture validation where media behavior changes.
- Security checks for Slack file access, path handling, secrets, limits, and cleanup.
- Fresh command output before any PASS or completion claim.

No live Slack workspace is assumed for the MVP QA process. Real Slack testing is a later environment decision.

## Scope Boundaries

The first implementation should not include permanent video storage, multi-workspace OAuth, subject tracking, automatic summaries after upload, arbitrary input formats, or production deployment.
