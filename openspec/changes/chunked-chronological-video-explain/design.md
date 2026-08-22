## Context

PR #8 already prevents unbounded frame Base64 from entering the textual Claude prompt and rejects requests that exceed the configured request budget. The controlled development smoke test still timed out, so the next change must reduce the work represented by each provider call without changing Slack scopes, provider limits, or the MVP media contract.

The current flow validates and downloads one MP4 into a private workspace, extracts representative frames, optionally prepares audio evidence, invokes the Claude boundary once, posts to the original thread, and cleans the workspace. This follow-up keeps that lifecycle and introduces temporal segmentation only for the explicit `explain` path. The worker owns Python, FFmpeg, Claude-boundary, tests, and fixture changes; Orca owns the OpenSpec, Trello, review, and functional QA gates.

## Goals / Non-Goals

**Goals:**

- Cover every validated MP4 interval from `0` through its probed duration without intentional gaps or overlaps.
- Use 10-second segments for videos up to 30 seconds and 30-second segments for longer videos, producing at most 10 segments for the 300-second MVP limit.
- Send each segment to an independent Claude request with no accumulated conversation and no evidence from another interval.
- Keep each request within the existing multimodal/request budgets and retain the prompt-injection, redaction, and private-path controls from PR #8.
- Render a chronological English thread response with segment boundaries, valid summaries/key points, supported timestamps, and explicit unavailable intervals.
- Keep validation, processing, and cleanup inside the existing asynchronous request lifecycle.

**Non-Goals:**

- Replace, rewrite, or merge PR #8; the implementation is a separate stacked follow-up PR.
- Change Socket Mode, Slack events/scopes, credentials, infrastructure, persistence, provider limits, or provider timeout policy.
- Enable Whisper or introduce timestamped transcript slicing. A global transcript without segment timestamps is not duplicated into every segment request; the segmented path may proceed with visual evidence and an evidence note.
- Implement export, crop, H.264/AAC, confirmation, or automatic explanation after upload.
- Claim Slack/Claude live behavior from mocks, fixtures, or CI. Any controlled smoke test is separate Functional Review evidence.

## Decisions

### 1. Deterministic adaptive segment plan

The media probe remains the source of truth for duration. A planner chooses a 10-second segment length when `duration_seconds <= 30` and a 30-second length otherwise. It emits half-open intervals `[start, end)` except that the final interval ends at the exact duration; timestamps are rounded only for FFmpeg arguments and display. The planner must cover a positive duration, preserve order, and produce no more than 10 intervals for the 300-second limit.

**Alternatives considered:** A fixed three-frame sampling strategy is cheaper but does not provide chronological coverage. A fully dynamic target-number algorithm would make output and cost less predictable. Overlapping windows could improve context at boundaries but duplicate evidence and provider cost, so they are deferred.

### 2. Segment-local visual evidence in one private workspace

Validation, download, and optional audio preparation happen once. FFmpeg then writes each segment's frames beneath a controlled per-segment directory in the same private workspace. Each segment samples at most three JPEGs at its start, midpoint, and end-with-margin; duplicate timestamps in very short intervals are removed. Frame labels and absolute timestamps are data values, not paths or instructions.

**Alternatives considered:** Creating a new workspace per segment would simplify isolation but multiplies download/probe work and complicates cleanup. Reusing the existing full-video frame set cannot guarantee temporal coverage. Extracting the full video as a new encoded clip is more expensive than seeking frames and is unnecessary for visual evidence.

### 3. Independent Claude calls with the existing boundary

The orchestrator builds one `AnalysisRequest` per segment and invokes the existing analyzer boundary sequentially in chronological order. Each request contains only the segment's frames and a bounded user instruction that names its interval; `build_prompt_envelope` remains the final budget guard and the multimodal image blocks remain separate from the textual JSON metadata. The same analyzer factory may be reused because each `analyze` call is a fresh provider query with no conversation history, but no request may include previous results as prompt context and no automatic retry is added.

Audio/transcript text is not repeated across segment requests. If a future transcriber supplies segment-addressable evidence, it can be added behind the existing boundary; this change treats an unsegmented transcript as unavailable for the segmented request and tells the renderer that visual evidence was used.

**Alternatives considered:** Sending the full transcript to every segment would duplicate sensitive content and consume the budget. Sharing a Claude conversation would reduce prompt repetition but risks cross-interval contamination and makes ordering/failure recovery ambiguous. Parallel calls could reduce wall-clock time but increase provider pressure and complicate deterministic cleanup, so sequential calls are the initial implementation.

### 4. Explicit fatal versus segment-local failures

Download, MP4 validation, duration/size limits, missing Claude configuration, and a failure before any segment can be prepared are fatal and use the existing safe failure path. A timeout, request-budget failure, provider failure, invalid structured response, or isolated frame extraction failure for one segment is segment-local: the orchestrator records a redacted unavailable interval, continues with later segments, and never uses the failed segment as evidence. If no segment returns a valid result, the orchestrator posts no partial explanation and uses a safe failure message.

**Alternatives considered:** Failing the entire request on one provider timeout preserves all-or-nothing behavior but discards valid chronology. Silently skipping a failed interval could make the user believe the timeline was complete. An explicit gap preserves useful verified results while keeping uncertainty visible.

### 5. Chronological renderer and Slack publication

Successful segment results are retained in planner order, never sorted by model wording. The renderer emits English section headers with absolute interval boundaries, then that segment's summary and key points. Model timestamps are included only when the structured result marks them available; segment boundaries are context and are not presented as model-derived observations. Failed intervals are rendered as an explicit unavailable note. The implementation must keep publication on the original `channel`/`thread_ts` and may split output only at segment boundaries if a Slack-safe message limit requires it; it must never split a sentence into an ambiguous interval.

**Alternatives considered:** One global synthesis call could produce a smoother narrative but reintroduces the original context/timeout risk and can fabricate missing intervals. Posting one unlabelled message per segment makes gaps and order harder to understand. Grouped, labelled output preserves the existing one-request user experience while making evidence boundaries visible.

### 6. Cleanup and security boundary

The existing `finally` cleanup remains the single owner for source video, segment frames, audio, transcripts, and intermediate artifacts. Segment results contain only structured text and timestamps after analysis; they must not retain local paths, Slack URLs, tokens, or raw media. Cleanup is attempted after success, partial success, fatal failure, timeout, and cancellation, with only redacted operational diagnostics.

### 7. Validation evidence

Unit tests use a deterministic segment planner, fake analyzer, fake Slack client, and failure-injection fakes. FFmpeg/FFprobe fixtures validate 25-second and 65-second examples where practical; planner tests cover the 300-second boundary without requiring a long generated file. CI and local checks validate Python 3.10/3.14 compatibility, OpenSpec, compileability, diff hygiene, budget behavior, and secret redaction. No worker test calls Slack or Anthropic; a coordinator-run smoke test with an approved non-sensitive MP4 remains a separate Functional Review gate.

## Risks / Trade-offs

- **More provider calls increase latency/cost** → Cap the plan at 10 calls, run sequentially, avoid automatic retries, and record the segment count in non-sensitive diagnostics only.
- **A segment can timeout while later segments succeed** → Continue only for segment-local errors and render an explicit unavailable interval; fail safely when all segments fail.
- **Visual-only evidence can miss spoken narration** → Do not claim transcript coverage; include an evidence note and defer timestamped transcript slicing to a separate approved change.
- **Model timestamps can be inaccurate or cross interval boundaries** → Preserve absolute frame/segment context, include model timestamps only when the result marks them available, and never convert segment boundaries into model claims.
- **Aggregated output can exceed Slack message limits** → Keep a stable bounded renderer and split only between labelled segments when required; test the ordering and gap markers.
- **Temporary segment artifacts could be retained** → Keep one `finally` cleanup boundary and test every terminal state, including partial and timeout paths.
- **The original timeout may be provider/runtime related rather than payload size** → Treat segmented requests as a bounded mitigation, retain the existing timeout/error evidence, and do not claim that chunking alone proves live provider success.

## Migration Plan

1. Add the new OpenSpec change and card, then branch from PR #8's head without changing PR #8.
2. Add planner and segment-evidence domain seams, update the orchestrator and renderer, and keep Slack handlers unchanged except for the existing enqueue path's delegated behavior.
3. Add mock/failure tests and repository-owned FFmpeg/FFprobe fixture coverage; update the new OpenSpec artifacts in the same PR.
4. Run local validation and CI. Code Review must pass before any Functional Review.
5. If approved, run a controlled smoke test with a non-sensitive MP4 and record the result without secrets or media; rollback is reverting the follow-up PR, leaving PR #8 intact.

## Open Questions

- No blocking product questions remain for this implementation: the user approved chronological narration, a separate follow-up, and adaptive 10/30-second segmentation. Live provider success remains an explicit QA gate, not an assumption of the design.
