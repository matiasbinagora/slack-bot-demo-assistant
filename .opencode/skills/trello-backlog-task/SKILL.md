---
name: trello-backlog-task
description: Trello backlog task structure and workflow rules. Use when any agent creates, reads, updates, comments on, validates, or moves Trello backlog cards, tasks, features, blockers, or implementation/review workflow items.
---

# Trello Backlog Task

Use this skill whenever Trello is involved in backlog, implementation, review, or release workflow.

Trello cards are the source of truth for task scope, acceptance criteria, status, and review decisions.

## Card Content Index

Use this index before acting on any Trello backlog card.

| Trello area | What to read | Used by |
| --- | --- | --- |
| Card title | Task type, unique numerical ID, short title | All agents |
| Card description: `ID` | Canonical task identifier | All agents |
| Card description: `Type` | Whether the card is a task or feature | All agents |
| Card description: `Title` | Human-readable task name | All agents |
| Card description: `Description` | Full product or technical intent and implementation context | All agents |
| Card description: `Requirements` | Required behavior, constraints, and implementation obligations | Developer, Code Reviewer, Functional Reviewer |
| Card description: `Acceptance Criteria` | Step-by-step validation contract | Developer, Code Reviewer, Functional Reviewer |
| Card description: `OpenSpec` | OpenSpec change/spec reference or documented exception | All agents |
| Card description: `Predecessors` | Blocking or prerequisite task IDs | All agents |
| Trello list | Current task status | All agents |
| Card comments | Prior decisions, blockers, review outcomes, transition history, and validation evidence | All agents |
| Attachments and PR links | Pull request, supporting evidence, screenshots, logs, or related artifacts | Developer, Code Reviewer, Functional Reviewer |

## Required Read Order

Before acting on a Trello card, read in this order:

1. Card title.
2. Current Trello list/status.
3. Full card description.
4. `Predecessors` section.
5. Latest relevant comments.
6. OpenSpec reference or exception.
7. Attachments and PR links when implementation or review depends on them.

## Agent-Specific Required Reads

Orchestrator must read:

- Card title
- Current status/list
- Full description
- Requirements
- Acceptance Criteria
- Predecessors
- Latest comments

Developer must read:

- Card title
- Current status/list
- Description
- Requirements
- Acceptance Criteria
- Predecessors
- Latest comments
- PR/branch guidance if already present

Code Reviewer must read:

- Card title
- Current status/list
- Description
- Requirements
- Acceptance Criteria
- Predecessors
- Developer completion comments
- PR link and validation evidence

Functional Reviewer must read:

- Card title
- Current status/list
- Description
- Requirements
- Acceptance Criteria
- Predecessors
- Code review outcome
- PR link, screenshots, logs, or runtime validation evidence when present

## Core Rules

- Read the Trello card before acting on it.
- Treat the card title, description, comments, and current list as the task contract.
- Do not start implementation or review from assumptions outside the card.
- Do not change unrelated cards.
- Do not skip required workflow statuses.
- Add a Trello comment for every status transition.
- Keep comments factual, concise, and useful for the next agent.

## Required Card Title

Every backlog card must use this project title format:

```text
DAY-<day>-<TYPE>-<ID> <Title>
```

Examples:

```text
DAY-1-TASK-001 Add user settings persistence
DAY-2-FEATURE-007 Add ordered history screen for verification
```

Rules:

- `DAY-<day>` must identify the planned delivery day.
- `TYPE` must identify the card kind.
- `ID` must be a unique numerical identifier.
- Use zero-padded IDs when possible, for example `001`, `002`, `010`.
- `Title` must be short, specific, and understandable without opening the card.
- A card may be named as either a task or a feature.
- Prefer `FEATURE` for user-visible product behavior.
- Prefer `TASK` for technical, setup, refactor, infrastructure, or support work.

## Required Card Description

Every backlog task must include these sections:

```markdown
ID
DAY-<day>-<TYPE>-<ID>

Type
<Task or Feature>

Title
<Short title>

Description
<Complete task description. Include enough context for a developer agent to implement the work and for reviewer agents to validate the implementation against the requested behavior.>

Requirements
- <Requirement 1>
- <Requirement 2>
- <Requirement 3>

Acceptance Criteria
1. <Step-by-step acceptance criterion 1>
2. <Step-by-step acceptance criterion 2>
3. <Step-by-step acceptance criterion 3>

Predecessors
- <DAY-<day>-<TYPE>-ID Title or None>

OpenSpec
<OpenSpec Change: change-id, OpenSpec Spec: spec-id, or OpenSpec Exception: reason>
```

## Description Requirements

The `Description` section must explain:

- What needs to be changed or created.
- Why the task exists.
- Who or what benefits from the change.
- Important behavior expected from the implementation.
- Relevant constraints, edge cases, or known risks.
- Any relationship to existing behavior or previous tasks.

The description must be complete enough that:

- A developer agent can implement without guessing the product intent.
- A code reviewer can verify technical correctness against scope.
- A functional reviewer can validate behavior against acceptance criteria.

If the description is incomplete, the agent must ask for clarification or mark the card as not ready.

## Requirements

The `Requirements` section must list concrete implementation or behavior requirements.

Good requirements are:

- Specific
- Testable
- Relevant to the task scope
- Free of unrelated nice-to-have work

Avoid vague requirements such as:

```text
- Make it better
- Improve UX
- Refactor as needed
```

Prefer concrete requirements such as:

```text
- Persist the selected workspace across app reloads.
- Show a loading state while the transcript export is being generated.
- Return a validation error when the meeting title is empty.
```

## Acceptance Criteria

The `Acceptance Criteria` section must be step-by-step and verifiable.

Each criterion must describe an observable result that a reviewer can validate.

Use numbered criteria:

```markdown
Acceptance Criteria
1. Given a user opens the settings page, when they change the workspace, then the new workspace is saved.
2. Given the user reloads the app, when the settings page opens again, then the previously selected workspace is shown.
3. Given saving fails, when the error is returned, then the user sees an accessible error message.
```

Acceptance criteria must not describe implementation details unless the implementation detail is part of the requested behavior.

## Predecessors

The `Predecessors` section identifies tasks that must be completed before this task can be started, reviewed, or released.

Use:

```markdown
Predecessors
- None
```

Or:

```markdown
Predecessors
- DAY-1-FEATURE-003 Add transcript import flow
- DAY-1-TASK-004 Add transcript persistence schema
```

Rules:

- Always include the section.
- Use task IDs when known.
- If a predecessor blocks the current task, do not move the card to `ready` or `in progress`.
- If a blocker is discovered later, add a comment explaining the blocker and reference the predecessor or follow-up task ID.

## Valid Statuses

A Trello card status is represented by its list.

Valid statuses:

```text
backlog
ready
in progress
code review
functional review
blocked
ready to release
done
```

## Status Meaning

`backlog`

The task is captured but may not be ready for implementation.

`ready`

The task has enough detail to implement, including title, description, requirements, acceptance criteria, and predecessors.

`in progress`

A developer agent is actively implementing the task.

`code review`

Implementation is complete and awaiting technical review.

`functional review`

Technical review has passed and the task is awaiting acceptance/runtime validation.

`blocked`

The task cannot proceed because of missing information, failed validation, dependency issues, or a discovered blocker.

`ready to release`

Functional review has passed and the task is ready for final release or closure.

`done`

The task is complete and all required gates have passed.

## Required Transition Comment

Every status transition must add a comment to the Trello card.

Use this format:

```markdown
Status transition

Agent: <agent name>
Task: <DAY-<day>-<TYPE>-ID>
Previous status: <previous status>
New status: <new status>
Reason: <why the transition is happening>

Summary:
- <What changed, was validated, or was decided>
- <Important context for the next agent>

Validation:
- <Command/result, manual check, PR review, or Not run with reason>

Remaining issues:
- <None or list of remaining risks/blockers>
```

## Transition Rules

- Validate the current card status before moving it.
- Do not transition a card if the required description fields are missing.
- Do not move a card to `ready` unless the task is implementable without major clarification.
- Do not move a card to `code review` unless implementation is complete and validation evidence is documented.
- Do not move a card to `functional review` unless code review passed.
- Do not move a card to `ready to release` unless functional review passed.
- Do not move a card to `done` unless final release/closure rules are satisfied.
- When blocking a card, explain the blocker clearly and identify the next action.

## Agent Responsibilities

Orchestrator:

- Creates and refines backlog cards.
- Ensures task cards are complete before moving them to `ready`.
- Splits large or ambiguous work into smaller cards.
- Ensures predecessors are documented.
- Performs final release/closure decisions when required.

Developer:

- Reads the full card before implementation.
- Implements only the described scope.
- Uses requirements and acceptance criteria as the implementation contract.
- Adds progress comments when useful.
- Moves eligible work from `ready` to `in progress`.
- Moves completed implementation from `in progress` to `code review`.
- Does not move work to `functional review`, `ready to release`, or `done`.

Code Reviewer:

- Reviews the implementation against the card description, requirements, and acceptance criteria.
- Adds inline PR comments when specific code changes are required.
- Approves or requests changes according to technical findings.
- Moves passing work from `code review` to `functional review`.
- Moves failing work from `code review` to `blocked`.
- Does not implement fixes.

Functional Reviewer:

- Validates runtime behavior against the card acceptance criteria.
- Confirms the user-facing or operational outcome matches the backlog task.
- Moves passing work from `functional review` to `ready to release`.
- Moves failing work from `functional review` to `blocked`.
- Does not modify code.

## Card Completeness Checklist

Before treating a card as ready, verify:

- Title follows `DAY-<day>-<TYPE>-<ID> <Title>`.
- ID is unique and numerical.
- Type is present.
- Title is present.
- Description is complete.
- Requirements are listed.
- Acceptance criteria are numbered and verifiable.
- Predecessors are listed or explicitly set to `None`.
- OpenSpec change/spec reference or exception is documented.
- Current status matches the Trello list.
- Blockers or dependencies are documented in comments when applicable.

If any required item is missing, do not proceed as if the card is ready.
