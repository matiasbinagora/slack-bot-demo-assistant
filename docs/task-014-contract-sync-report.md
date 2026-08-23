# TASK-014 docs correction report

- Scope: corrected the OpenSpec contract omission so supported explanation cleanup terminal states now explicitly include Slack publish failure.
- Updated files:
  - `openspec/changes/mvp-slack-video-assistant/tasks.md`
  - `openspec/changes/mvp-slack-video-assistant/design.md`
  - `openspec/changes/mvp-slack-video-assistant/specs/video-understanding/spec.md`
  - `docs/task-014-contract-sync-report.md`
- Preserved exclusions and follow-ups:
  - active explanation cancellation remains excluded from the current MVP contract
  - approved follow-up remains `explanation-job-cancellation` / `DAY-8-TASK-015`
  - pending export cancellation remains preserved as already supported behavior
- Not changed:
  - no `src/**` edits
  - no `tests/**` edits
  - no cancellation implementation or behavior changes
  - no Slack/Claude/FFmpeg/export contract expansion beyond the documented omission fix
