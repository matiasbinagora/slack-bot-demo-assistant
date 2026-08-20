---
name: openspec-workflow
description: Operate the repository's OpenSpec lifecycle for exploration, proposals, artifact completion, validation, and review evidence. Use when planning or validating a scoped change.
---

# OpenSpec Workflow

This repository uses the `spec-driven` OpenSpec schema from `openspec/config.yaml`.

## Commands

- `openspec list --json` to discover changes.
- `openspec status --change "<name>" --json` to inspect artifact state.
- `openspec instructions <artifact> --change "<name>" --json` to get the next artifact contract.
- `openspec validate "<name>" --json` to validate a change or spec.
- `openspec doctor --json` to inspect relationship health.

## Rules

- Read the artifact instructions and completed dependencies before writing an artifact.
- Ask when scope, acceptance criteria, or validation is ambiguous.
- Do not call a change implementation-ready while required artifacts are incomplete.
- Do not mark functional review PASS when OpenSpec validation is missing or failed unless an accepted exception is recorded.
- Keep application implementation separate from planning artifacts.
