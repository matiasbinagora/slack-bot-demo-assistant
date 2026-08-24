# Local Slack App and Socket Mode setup

This document covers the local-only Slack foundation implemented for `DAY-2-TASK-002` and the interactive export ratio selection added in `DAY-12-TASK-018`.

## Scope of this setup

- Python Slack Bolt application startup through Socket Mode.
- Environment-backed configuration for `SLACK_BOT_TOKEN` and `SLACK_APP_TOKEN` only.
- Python 3.10 or newer for the local editable install and test workflow.
- Secret-free local setup instructions.

## Out of scope for this slice

- Live Slack workspace QA.
- Public HTTP webhook / Events API deployment.
- Live Slack workspace QA claims beyond explicitly run local/manual evidence.
- Public HTTP webhook / Events API deployment.
- Persistent storage, arbitrary ratios, smart crop, padding, or credential value changes.

## Environment variables

Set Slack credentials in the local process environment only:

```text
SLACK_BOT_TOKEN=
SLACK_APP_TOKEN=
LOG_LEVEL=INFO
```

Do not commit tokens, workspace URLs, channel IDs, or private Slack file links.

## Clean-checkout local environment

Use a local Python 3.10+ interpreter and create the virtual environment from a clean checkout:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .
python -m pip install -e ".[dev]"
```

The `-e .` command installs the local package entrypoint, and `-e ".[dev]"` adds the approved test dependency set for repository validation.

## Entrypoint

Use one of these local entrypoints after creating the local virtual environment and installing the package:

```text
.venv/bin/python -m slack_video_assistant
slack-video-assistant
```

If either Slack token is missing, the process exits safely and logs a configuration error without printing token values or private URLs.

## Slack App configuration

1. Create a Slack app for local development.
2. Enable **Socket Mode**.
3. Do **not** configure a public HTTP Events API webhook for this MVP foundation.
4. Configure currently known scopes:
   - `files:read`
   - `chat:write`
5. Configure the currently known event subscription:
    - `file_shared`
6. Configure the currently known thread message subscription used by the local command flow:
    - `message` events for `explain`, `export`, `confirm`, and `cancel`
7. Enable **Interactivity & Shortcuts** for the same app so Slack can deliver the export ratio `static_select` action through Socket Mode.
8. Keep Socket Mode as the transport. Do **not** add a public request URL for this MVP slice.

## Export ratio interaction

- The `export` command posts a Block Kit `static_select` in the same thread.
- The only approved export ratios are `16:9`, `9:16`, `1:1`, `4:3`, and `3:4`.
- `16:9` is selected by default.
- Changing the ratio only updates the pending suggestion. It does **not** download media, run FFmpeg, run FFprobe export validation, or publish an output.
- Users still reply with typed `confirm` to start the export or `cancel` to stop it.

## Pending workspace-dependent permissions

The exact additional permissions may vary by workspace policy, channel type, and the first authorized live test environment. Those permissions remain pending confirmation and must not be changed silently in code or docs.

## Local validation

- Tests run with mocked Slack Bolt / Socket Mode behavior only.
- Interactive action coverage also uses mocked Slack payloads and mocked clients only.
- No Slack credentials are required for the repository test suite.
- No live network, live Slack workspace, or live Claude account is required for this task.
- Slack live QA and Claude live calls were not run for this repository slice unless separately recorded as manual evidence.
