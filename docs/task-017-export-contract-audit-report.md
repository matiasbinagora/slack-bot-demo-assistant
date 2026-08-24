# DAY-8-TASK-017 export contract audit report

## Scope completed

- Audited the implemented export flow against the `mvp-slack-video-assistant` OpenSpec export contract only; no Python, FFmpeg, FFprobe, Slack, Claude, fixture, retention, scope, or credential behavior changed.
- Confirmed the current implementation and tests already cover supported export ratios, explicit confirm/cancel behavior, the no-FFmpeg-before-confirm gate, centered crop generation, H.264/AAC output, FFprobe validation, validate-publish-cleanup ordering, and failure cleanup.
- Marked only OpenSpec task `5.4` complete after collecting fresh graph, code, and validation evidence and recording the traceable matrix below.

## Files changed

- `docs/task-017-export-contract-audit-report.md`
- `openspec/changes/mvp-slack-video-assistant/tasks.md`

## Graph evidence

- Graphify graph path: `/Users/matiasbinagora/Projects/slack-bot-video-assistant/.worktrees/slack-bot-video-assistant-task-017-sync-export-openspec/graphify-out/graph.json`
- Graphify preflight: graph missing in this exact worktree; Orca approved a local refresh for this worktree only.
- Graphify refresh command/result: `graphify update .` → **1454 nodes / 2563 edges / 102 communities**.
- Graphify scoped query: `export confirmation FFmpeg FFprobe cleanup thread publish validation ordering` (BFS depth 2).
- Codebase Memory project: `slack-bot-video-assistant-task-017-sync-export-openspec`
- Codebase Memory preflight: no projects indexed; Orca approved indexing this exact worktree only.
- Codebase Memory refresh evidence: `index_repository(..., mode="moderate")` → status `indexed`, **1412 nodes / 4093 edges**.
- Codebase Memory scoped queries used:
  - `get_architecture(aspects=["overview","entry_points","languages","clusters"])`
  - `search_graph(query="export confirmation ffmpeg ffprobe cleanup publish")`
  - `search_graph(qn_pattern=".*ThreadSessionStore\\.apply_command|.*SlackEventHandler\\.handle_message")`
  - `get_code_snippet(export_video)`
  - `get_code_snippet(validate_exported_video)`
  - `get_code_snippet(_export_ffmpeg_command)`
  - `get_code_snippet(ThreadSessionStore.apply_command)`
  - `get_code_snippet(SlackEventHandler.handle_message)`
  - `get_code_snippet(ExportOrchestrator)`
  - `get_code_snippet(test_export_video_creates_valid_centered_h264_aac_mp4_for_supported_ratios)`
  - `get_code_snippet(test_export_orchestrator_publishes_validated_output_before_cleanup)`
  - `get_code_snippet(test_export_orchestrator_rejects_invalid_output_without_publication_and_cleans_up)`
  - `get_code_snippet(test_export_orchestrator_logs_redacted_upload_failure_and_attempts_cleanup)`
  - `get_code_snippet(test_session_store_rejects_out_of_order_confirm_and_duplicate_export)`
  - `get_code_snippet(test_cancel_pending_export_clears_state_without_executor_side_effects)`
  - `get_code_snippet(test_confirm_without_export_executor_reports_saved_confirmation_without_handoff_claim)`

## Files opened after graph selection

- `src/slack_video_assistant/media_pipeline.py`
- `src/slack_video_assistant/export_orchestrator.py`
- `src/slack_video_assistant/session_store.py`
- `src/slack_video_assistant/slack_events.py`
- `tests/test_media_pipeline.py`
- `tests/test_export_orchestrator.py`
- `tests/test_session_store.py`
- `tests/test_slack_events.py`
- `pyproject.toml`
- `openspec/changes/mvp-slack-video-assistant/specs/video-export/spec.md`
- `openspec/changes/mvp-slack-video-assistant/design.md`
- `openspec/changes/mvp-slack-video-assistant/tasks.md`

## Contract / evidence matrix

| Contract item | Implementation evidence | Test / audit evidence | Result |
| --- | --- | --- | --- |
| Supported ratios limited to `16:9`, `9:16`, `1:1` | `media_pipeline.export_video`, `_export_ffmpeg_command`, and `_require_supported_export_ratio` gate exports to supported ratios; session suggestion uses the default supported ratio `16:9`. | `tests/test_media_pipeline.py::test_export_video_creates_valid_centered_h264_aac_mp4_for_supported_ratios` covers `16:9`, `9:16`, and `1:1`. | In sync |
| Explicit `export` suggestion with centered-crop explanation and pending confirmation | `ThreadSessionStore.apply_command` moves a valid session to `EXPORT_PENDING`; `SlackEventHandler.handle_message` routes thread commands through session state. | `tests/test_session_store.py::test_session_store_rejects_out_of_order_confirm_and_duplicate_export` plus `tests/test_slack_events.py` confirm pending state and thread command handling. | In sync |
| No FFmpeg before explicit `confirm` | `SlackEventHandler.handle_message` submits export work only in the `CONFIRM` branch when `result.export_request` exists; `ExportOrchestrator` is not called on bare `export` or `cancel`. | `tests/test_confirm_without_export_executor_reports_saved_confirmation_without_handoff_claim` and `tests/test_cancel_pending_export_clears_state_without_executor_side_effects` prove confirm/cancel behavior without premature executor side effects. | In sync |
| `cancel` clears only pending export confirmation and reports cancellation in English | `ThreadSessionStore.apply_command` converts `EXPORT_PENDING` to `CANCELLATION_CONSUMED`. | `tests/test_cancel_pending_export_clears_state_without_executor_side_effects` asserts no export submission and the English cancellation messages. | In sync |
| Confirmed export uses centered crop and does not overwrite source | `media_pipeline.export_video` computes `_centered_crop_geometry`, writes to `exports/<ratio>.mp4`, and returns a distinct output path. | `tests/test_export_video_creates_valid_centered_h264_aac_mp4_for_supported_ratios` asserts expected dimensions, valid output, and unchanged source bytes. | In sync |
| Output must be MP4 with H.264 video and AAC audio | `_export_ffmpeg_command` emits `libx264` and `aac`; `validate_exported_video` rejects non-H.264 or non-AAC output. | `tests/test_export_video_creates_valid_centered_h264_aac_mp4_for_supported_ratios` and `tests/test_validate_exported_video_rejects_unexpected_codecs` cover valid/invalid codecs. | In sync |
| FFprobe validates container, dimensions, codecs, and usable duration before publish | `probe_video` enforces MP4 container, readable duration, stream presence, and dimensions; `validate_exported_video` adds codec and expected-dimension checks before Slack upload. | Code audit of `probe_video` and `validate_exported_video`; full pytest and local FFprobe-backed fixture tests cover these seams. | In sync |
| Publish only after validation, then cleanup | `ExportOrchestrator._run` executes `probe_video` → `export_video` → `validate_exported_video` → `_upload_export`, then `workspace.cleanup(...)` in `finally`. | `tests/test_export_orchestrator.py::test_export_orchestrator_publishes_validated_output_before_cleanup` asserts call order `validate`, `publish`, `cleanup`. | In sync |
| Invalid or partial output must not publish and cleanup must still run | `ExportOrchestrator._run` catches validation/publish failures, posts an English failure, and always attempts cleanup in `finally`. | `tests/test_export_orchestrator_rejects_invalid_output_without_publication_and_cleans_up` and `tests/test_export_orchestrator_logs_redacted_upload_failure_and_attempts_cleanup` cover validation failure, publish failure, cleanup state, and redacted diagnostics. | In sync |
| Local QA only; no live Slack or Anthropic claim | Repository contract and this task remain mock/fixture based only. | Fresh validation below plus explicit boundary statement in this report. | In sync |

## Findings

- No real export-contract divergence requiring spec or design text changes was found in this task worktree.
- The current implementation satisfies the audited OpenSpec export contract with local mock/fixture evidence only; this task does not claim live Slack workspace or live Anthropic QA.
- Because no behavior divergence was found, the only OpenSpec change needed here was marking task `5.4` complete and attaching this audit matrix.
- Dependency/bootstrap note: `.venv` was missing in this worktree, so Orca approved `python3 -m venv .venv && .venv/bin/python -m pip install -e ".[dev]"`; no production files or credentials were changed.

## Validation

- Full suite: `./.venv/bin/python -m pytest` → **128 passed**
- Bytecode: `./.venv/bin/python -m compileall -q src tests` → **passed**
- OpenSpec validate: `openspec validate "mvp-slack-video-assistant" --json` → **valid true**
- OpenSpec doctor: `openspec doctor --json` → **healthy true**
- Diff check: `git diff --check` → **passed**
- FFmpeg availability: `ffmpeg -version` → **installed (8.0)**
- FFprobe availability: `ffprobe -version` → **installed (8.0)**
- Lint/type checks: repository still exposes no configured lint or type-check command in `pyproject.toml`; document as unavailable unless new evidence appears.
- Safe added-line secret review: changed files were reviewed via `git diff`; no live token, private Slack URL, webhook, key material, transcript content, or media payload was added.

## QA boundary statement

- No live Slack workspace QA occurred.
- No live Anthropic/Claude API calls occurred.
- All evidence in this audit comes from repository-owned fixtures, local FFmpeg/FFprobe execution, mocks/fakes, graph context, and OpenSpec validation.

## Remaining risks

- This audit proves contract alignment for the current local implementation only; it does not verify workspace permissions, real Slack delivery, or live Anthropic behavior.
- The repository still lacks configured lint/type automation, so static analysis remains limited to compileall plus test execution.
