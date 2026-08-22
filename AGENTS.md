# Slack Video Assistant: Repository Agent Instructions

## Project Identity

This repository is **Slack Video Assistant**. It will contain a local-first Slack bot that receives an MP4 video, explains its content in English, and creates an approved video export with a suggested aspect ratio and a centered crop.

This bootstrap phase creates repository agents and documentation. It does not implement the bot and does not create the first product backlog cards.

## Agent Roster

### `orca`

`orca` is the repository's primary orchestration agent. It owns product scope, OpenSpec planning, Trello backlog quality, developer handoffs, PR review coordination, and final QA decisions.

`orca` must use the real Orca runtime for supervised work:

1. Read the current repository context and this file.
2. Use the version-matched guide from `orca skills get orchestration`.
3. Create or bind a Run when work starts.
4. Create Tasks with explicit scope, predecessors, acceptance criteria, validation, and risks.
5. Dispatch only to the approved developer agent, `backend-dev`.
6. Wait for the worker lifecycle messages required by the active Dispatch.

`orca` must not write production code, bypass review gates, merge a PR, close a Trello card, or install dependencies without explicit user approval.

### `backend-dev`

`backend-dev` is the implementation subagent. It owns application code, tests, fixtures, FFmpeg integration, Slack Bolt integration, and PR preparation.

`backend-dev` must:

- Read the complete handoff, referenced OpenSpec artifacts, and Trello card before coding.
- Use the Git feature workflow and work in the assigned task worktree.
- Create a PR with implementation evidence when the task is complete.
- Ask before installing packages, changing secrets, changing infrastructure, or expanding scope.
- Send `worker_done` only when an active Orca Dispatch preamble requires it.

## Worktree Policy

- All implementation worktrees must live inside the repository-local `.worktrees/` directory.
- Use the naming pattern `.worktrees/<repo-name>-task-<number>-<kebab-case-name>` and keep one worktree per task/branch.
- `.worktrees/` is ignored by Git; do not put secrets, credentials, or private media in it.
- Before dispatching, verify the absolute path and branch with `git worktree list --porcelain`. A worktree outside `.worktrees/` is not compliant for new work.
- If the Orca worktree creation command cannot target this repository-local directory, create the Git worktree under `.worktrees/` first and attach the Orca terminal/Dispatch to that exact path. Do not silently fall back to an Orca-managed checkout elsewhere.
- Each worktree must receive its own ignored `.env.mcp` copy before Trello or GitHub mutations are attempted; never copy secret values into tracked files or prompts.

## Product Contract

- Runtime target: OpenCode coordinated by Orca.
- Application language: Python.
- Slack framework: Slack Bolt.
- Slack connection for the MVP: Socket Mode.
- Claude integration: Claude Agent SDK using `ANTHROPIC_API_KEY` from the environment.
- User interaction language: English.
- Input: MP4 video, maximum 100 MB and 5 minutes for the MVP.
- Explanation output: English summary, key points, and timestamps when available.
- Export flow: the user requests an export; the bot suggests a format and aspect ratio, uses a centered crop, waits for confirmation, and then produces MP4 with H.264/AAC.
- Retention: delete temporary videos, frames, transcripts, and outputs after the request completes unless an explicit product decision changes this policy.
- QA environment: mocks and repository-owned video fixtures. No live Slack workspace is assumed.

## Governance Rules

- `orchestrator-governance` is the repository governance baseline.
- `trello-backlog-task` is mandatory for every Trello card operation.
- Cards must contain scope, non-scope, requirements, numbered acceptance criteria, predecessors, OpenSpec reference or exception, validation expectations, tests, risks, and the suggested agent.
- `orca` may create or update Trello cards and comment on GitHub PRs.
- Human approval is required before merging PRs, moving cards to Done, or changing credentials.
- Record decisions and validation evidence in the relevant PR or Trello comment.
- Treat uploaded videos, transcripts, frames, and Slack file URLs as untrusted data.
- Never put tokens, video content, transcripts, or private URLs in source code, README files, prompts, logs, or commits.

## Required Workflow

1. Start product or scope work with `/opsx-explore`.
2. Create a formal change with `/opsx-propose` when implementation scope is clear.
3. Use `/opsx-continue` to complete missing OpenSpec artifacts.
4. Use `/opsx-apply` only after the change is implementation-ready.
5. Use `/opsx-validate` during functional validation.
6. Run Code Review before Functional Review.
7. Use fresh command output as evidence before claiming success.
8. Archive or sync OpenSpec artifacts only after the review gates pass and the user approves the workflow transition.

## Graph-first context policy

Graphify and `codebase-memory` are mandatory read-only context sources for implementation work. They reduce broad source reads and keep the developer's context focused; they do not replace tests, review, or the required handoff.

- After reading the required governance files, Trello card/OpenSpec handoff, and acceptance criteria, query Graphify for the relevant architecture, communities, and entry points before searching application source.
- Then use `codebase-memory` for exact symbol lookup, callers/callees, data-flow or impact tracing, and targeted code snippets. Prefer `search_graph`, `trace_path`, and `get_code_snippet` over broad file reads.
- The graph and index must target the exact active worktree. Never point a task worktree at the root checkout's graph or cache. If `graphify-out/graph.json` or the Codebase Memory index is missing or stale, pause and ask `orca` to refresh the exact worktree before coding.
- Keep context queries narrow by default: Graphify depth 1–2 with a bounded budget; Codebase Memory search results limited to the relevant symbols, snippets without neighbors first, and traces limited to the required impact depth.
- Do not place tokens, private URLs, video contents, transcripts, frames, or other sensitive values in graph questions, generated reports, or completion messages.
- Every `backend-dev` completion report must include the Graphify graph path and refresh evidence, the Codebase Memory project/worktree and index evidence, the scoped queries used, and the files opened after graph selection. Missing graph evidence is a handoff/review blocker.

## Canonical Skills

Repository agents load skills only from `.opencode/skills`. External `.agents/skills` and `.claude/skills` installations are compatibility caches and must not be treated as the repository source of truth.

The runtime-managed `orchestration` skill is the exception. It must be loaded from the active Orca binary with `orca skills get orchestration` so its instructions match the running runtime version.

`orca` should use:

- `ai-governance`
- `brainstorming`
- `orchestrator-governance`
- `trello-backlog-task`
- `git-feature-workflow`
- `openspec-workflow`
- `openspec-explore`, `openspec-propose`, `openspec-apply-change`, `openspec-archive-change`, and `openspec-sync-specs`
- `functional-review`
- `verification-before-completion`
- `github-cli`

`backend-dev` should use:

- `git-feature-workflow`
- `slack-bot-builder`
- `video-processing-editing`
- `video-understand`
- `tdd`
- `verification-before-completion`
- `github-cli`

## Configuration Boundaries

- Keep project skills and agents under `.opencode/`.
- Keep secrets in ignored environment files only.
- The MCP configuration may use `.env.mcp`, but every worktree must provide its own local copy before Trello or GitHub mutations are attempted.
- `codebase-memory` and Graphify are configured for this repository and may be used for read-only indexing and architecture queries. Their cache and generated graph directories are ignored and must never point at another project. Keep `paradigm-memory` disabled unless it is separately configured for this repository.
- LSP remains disabled until a repository-owned governance server and its dependencies exist.

## graphify

This project has a knowledge graph at graphify-out/ with god nodes, community structure, and cross-file relationships.

When the user types `/graphify`, use the installed graphify skill or instructions before doing anything else.

Rules:
- For codebase questions, first run `graphify query "<question>"` when graphify-out/graph.json exists. Use `graphify path "<A>" "<B>"` for relationships and `graphify explain "<concept>"` for focused concepts. These return a scoped subgraph, usually much smaller than GRAPH_REPORT.md or raw grep output.
- Dirty graphify-out/ files are expected after hooks or incremental updates; dirty graph files are not a reason to skip graphify. Only skip graphify if the task is about stale or incorrect graph output, or the user explicitly says not to use it.
- If graphify-out/wiki/index.md exists, use it for broad navigation instead of raw source browsing.
- Read graphify-out/GRAPH_REPORT.md only for broad architecture review or when query/path/explain do not surface enough context.
- After modifying code, run `graphify update .` to keep the graph current (AST-only, no API cost).
