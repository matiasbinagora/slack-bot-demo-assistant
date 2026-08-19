---
name: functional-review
description: Senior QA functional validation for acceptance criteria, runtime behavior, operational readiness, setup impact, and final readiness after Code Review passes.
---

# Functional Review

Use this skill when validating completed work after Code Review.

## Core Rules

- Start only after Code Review has passed when the PR workflow is used.
- Start functional validation through `/opsx-validate`.
- Read the Trello card before validating when Trello is used.
- Read the task description, requirements, acceptance criteria, comments, PR link, developer validation evidence, and code review outcome.
- Read the referenced OpenSpec change/spec or documented OpenSpec exception.
- Load `openspec-workflow` during validation.
- Validate behavior against the task contract, not only against the PR description.
- Validate behavior against the referenced OpenSpec artifacts when present.
- Validate runtime behavior when feasible.
- Treat `/opsx-validate` as the required workflow for OpenSpec behavioral conformance and acceptance validation.
- For frontend implementation cards, treat Playwright-backed runtime validation as mandatory.
- For frontend implementation cards, use reviewer-generated Playwright validation flows or commands mapped directly to the acceptance criteria unless a reusable project-owned validation flow already exists.
- Run operational checks when they materially improve confidence.
- Confirm setup, documentation, or environment impact when the task changes usage or setup.
- Document exactly what was and was not validated.
- Record detailed frontend runtime validation evidence in a PR comment and summarize the decision in Trello.
- Missing developer unit tests are a blocker unless the developer documented a valid exception and Code Review accepted it.
- Missing or failed OpenSpec validation is a blocker unless the developer documented a valid exception and Code Review accepted it.
- Do not return PASS on a frontend card without fresh browser-based validation evidence unless the Orchestrator documented an explicit non-frontend exception.
- Move Functional Review to Ready To Release only on PASS.
- Move Functional Review to Blocked on FAIL.
- Do not modify code.
- Do not perform technical PR review by default.
- Do not merge PRs or move tasks to Done.

## PASS Requirements

Return PASS only when:

- Acceptance criteria are satisfied.
- Referenced OpenSpec behavior is satisfied when a spec/change exists.
- Runtime or operational behavior matches the task definition.
- There are no unresolved blockers.
- Any skipped validation is documented and acceptable.
- Frontend cards include fresh Playwright-backed runtime evidence in the PR and Trello when required.

## FAIL Requirements

Return FAIL when:

- Any acceptance criterion is not satisfied.
- Runtime behavior cannot be validated and the gap affects confidence.
- A frontend card cannot produce sufficient Playwright-backed runtime evidence.
- The implementation behaves differently from the task contract.
- The implementation behaves differently from the referenced OpenSpec artifacts.
- Required tests are missing without accepted documented exception.
- Frontend runtime setup details are missing and materially prevent validation.
- Setup or operational readiness is broken.

## Output Format

```markdown
Decision: PASS | FAIL

Acceptance criteria validation:
1. <Criterion>: PASS | FAIL | NOT VERIFIED - <evidence>

Runtime validation:
- <Command or generated validation flow, URL/environment, screenshot/log, or not run with reason>

Findings:
- <SEVERITY> <finding>

Remaining risks:
- <None or risks>

Trello transition:
- <functional review -> ready to release | functional review -> blocked | not applicable>
```
