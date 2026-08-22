---
name: git-feature-workflow
description: Developer Git feature branch and worktree workflow. Use when starting implementation work, syncing from main, creating task feature branches, creating or reusing Git worktrees, naming branches from backlog task IDs, or preparing code changes before opening a PR.
---

# Git Feature Workflow

Use this skill before any developer agent edits implementation files.

This skill is the pre-coding Git setup gate for implementation tasks. It keeps task work isolated, branches predictable, and base branches fresh before code changes begin.

## Workflow Index

Use this index before creating a branch, creating a worktree, or editing implementation files.

| Workflow item | Source | Required before coding |
| --- | --- | --- |
| Task ID | Trello card title/description, issue, or user request | Yes |
| Numeric task number | Final numeric segment of the task ID, for example `DAY-2-TASK-007` -> `007` | Yes |
| Task title | Trello card title/description, issue, or user request | Yes |
| Kebab-case task title | Derived from task title | Yes |
| Base branch | Repository default, task instruction, or orchestrator instruction | Yes |
| Current Git status | `git status --short` | Yes |
| Latest remote refs | `git fetch origin` | Yes |
| Updated base branch | `git pull --ff-only origin <base>` | Yes |
| Feature branch | `feature/task-{number}-{kebab-case-name}` | Yes |
| Task worktree | Task-specific Git worktree path | Yes |
| Trello status | Trello card list, if Trello is used | Required when Trello is used |
| Setup report | Developer response/comment | Yes |

## Core Rules

- Create or reuse a task-specific Git worktree for every implementation task.
- Do not edit implementation files in the original repository root after implementation begins.
- Sync from the base branch before creating the task branch.
- Default base branch is `main` unless the task or repository explicitly says otherwise.
- Create one branch per backlog task.
- Do not mix unrelated tasks in one branch.
- Do not push directly to `main`.
- Do not use destructive Git commands unless explicitly approved.

## Required Inputs

Before creating a branch or worktree, identify:

- Task ID, for example `DAY-2-FEATURE-007` or `DAY-1-TASK-014`.
- Numeric task number, for example `007`.
- Task title.
- Kebab-case task title.
- Base branch, defaulting to `main`.
- Repository root path.
- Intended worktree path.

If any required input is unclear, ask for clarification before editing implementation files.

## Branch Naming

Use this branch format:

```text
feature/task-{number}-{kebab-case-name}
```

Examples:

```text
feature/task-007-add-ordered-history-screen-for-verification
feature/task-014-persist-user-settings
feature/task-021-add-transcript-export-endpoint
```

Rules:

- Use the final numerical task ID from the backlog card, issue, or user request.
- Preserve zero-padding when present.
- Use lowercase kebab-case for the title.
- Remove punctuation and special characters.
- Keep the branch name concise but recognizable.
- Use `feature/task-...` for both `TASK` and `FEATURE` backlog cards unless the orchestrator explicitly approves another prefix.

## Worktree Naming

Use this repository-local path format:

```text
.worktrees/{repo-name}-task-{number}-{kebab-case-name}
```

Example:

```text
.worktrees/meetscribe-flow-task-007-add-ordered-history-screen-for-verification
```

Rules:

- `.worktrees/` is the required root for all new task worktrees in this repository.
- Use one worktree per implementation task.
- Reuse an existing task worktree only if it belongs to the same task and branch.
- Do not share one worktree across unrelated tasks.
- Do not edit implementation files in the original project root after creating or identifying the task worktree.
- Do not create new task worktrees in a sibling directory, an Orca-global workspace directory, or an arbitrary temporary path.
- Report the worktree path in every developer handoff.

## Required Setup Order

Before editing code:

1. Read the task source.
2. If Trello is involved, load `trello-backlog-task` and confirm the card is ready.
3. Identify task ID, numeric task number, and task title.
4. Derive the branch name and worktree path.
5. Inspect Git status.
6. Fetch remote refs.
7. Sync the base branch.
8. Create or reuse the task worktree.
9. Confirm the feature branch is active inside the worktree and the absolute path is below `<repo-root>/.worktrees/`.
10. Update Trello status when Trello is used.
11. Report setup details before coding.

## Worktree Workflow

Use standard Git commands from the repository root to create or reuse task worktrees. Do not depend on shared scripts outside this project.

Run read-only/status checks first:

```bash
git status --short
git fetch origin
git branch --show-current
```

Sync the base branch:

```bash
git switch main
git pull --ff-only origin main
```

Create the task worktree and branch inside the repository:

```bash
git worktree add .worktrees/meetscribe-flow-task-007-add-ordered-history-screen-for-verification -b feature/task-007-add-ordered-history-screen-for-verification main
```

Then run all implementation commands from the new worktree path.

When Orca is supervising the task, bind the worker terminal to the exact absolute path returned by `git worktree list --porcelain`. If `orca worktree create` cannot place a checkout under `.worktrees/`, use `git worktree add` as above and then attach the Orca terminal/Dispatch with the path selector. The worker must not be dispatched into the default Orca workspace directory.

## Existing Worktree Reuse

Before creating a new worktree, check existing worktrees.

Reuse only when:

- The worktree path belongs to the same task.
- The branch name matches the expected feature branch.
- The worktree is not being used for another active task.
- The worktree has no unrelated changes.

If a matching worktree has unexpected changes, stop and ask the user or orchestrator before proceeding.

## Base Branch Sync Rules

- Fetch remote refs before syncing the base branch.
- Update the base branch with fast-forward only.
- Do not create a task branch from a stale local base branch.
- If fast-forward fails, stop and report the issue instead of rebasing or merging without approval.
- If the base branch is not `main`, report the explicit reason.

## Prohibited Actions

Do not:

- Edit implementation files in the original repository root.
- Start coding before branch/worktree setup is complete.
- Create branches from stale local `main`.
- Push directly to `main`.
- Mix unrelated task changes.
- Delete worktrees unless cleanup is explicitly requested.
- Delete branches unless explicitly requested.
- Use `git reset --hard`, `git checkout --`, or other destructive commands unless explicitly approved.

## Required Setup Report

Before coding, report:

```markdown
Git setup

Task: <DAY-<day>-<TYPE>-ID>
Base branch: main
Feature branch: feature/task-<number>-<kebab-title>
Worktree path: <absolute path>
Remote synced: yes/no
Trello status updated: <previous> -> <new> or Not applicable
```

## Handoff Requirements

Developer completion output must include:

- Task ID.
- Feature branch.
- Worktree path.
- Base branch.
- Commands run.
- Validation results.
- PR URL when available.
- Any remaining risks or blockers.
