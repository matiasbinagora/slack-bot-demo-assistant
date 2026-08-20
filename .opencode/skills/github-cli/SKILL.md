---
name: github-cli
description: Use the GitHub CLI for repository inspection, branches, pull requests, checks, comments, and workflow evidence while preserving approval gates. Use when an agent needs GitHub operations.
---

# GitHub CLI

Use current `gh` help and repository state rather than guessing flags.

- Read repository, branch, PR, check, and workflow state without mutation when possible.
- Create a PR only when the handoff explicitly requires it.
- Add review comments only with factual, file-specific evidence.
- Never expose tokens or secret values.
- Never delete repositories, releases, assets, secrets, variables, workflow runs, or caches.
- Do not merge a PR; `orca` requires human approval after Code Review and Functional Review.
- Include branch, worktree, commands, checks, and remaining risks in developer completion evidence.
