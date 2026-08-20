# Local Slack App and Socket Mode setup

This document covers the local-only Slack foundation implemented for `DAY-2-TASK-002`.

## Scope of this setup

- Python Slack Bolt application startup through Socket Mode.
- Environment-backed configuration for `SLACK_BOT_TOKEN` and `SLACK_APP_TOKEN` only.
- Python 3.10 or newer for the local editable install and test workflow.
- Secret-free local setup instructions.

## Out of scope for this slice

- Live Slack workspace QA.
- Public HTTP webhook / Events API deployment.
- Video processing, file downloads, thread command handlers, Claude integration, or persistent storage.

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
6. Keep future thread-message subscriptions pending confirmation for follow-up tasks:
   - thread messages for `explain`
   - thread messages for `export`
   - thread messages for `confirm`
   - thread messages for `cancel`

## Pending workspace-dependent permissions

The exact additional permissions may vary by workspace policy, channel type, and the first authorized live test environment. Those permissions remain pending confirmation and must not be changed silently in code or docs.

## Local validation

- Tests run with mocked Slack Bolt / Socket Mode behavior only.
- No Slack credentials are required for the repository test suite.
- No live network, live Slack workspace, or live Claude account is required for this task.
- Slack live QA and Claude live calls were not run for this repository slice.
