---
description: Validate an OpenSpec change and its acceptance evidence without modifying production code.
agent: orca
---

Use the `openspec-workflow` and `functional-review` skills to validate an OpenSpec change.

1. If `$ARGUMENTS` is empty, run `openspec list --json` and ask the user which active change to validate.
2. Run `openspec status --change "<change>" --json` and read every required artifact.
3. Run `openspec validate "<change>" --json`.
4. Read the relevant Trello card, PR link, developer evidence, and review outcome when they exist.
5. Validate acceptance criteria, tests, operational behavior, media fixtures, setup impact, and documented risks.
6. Return the `functional-review` output format with PASS, FAIL, or NOT VERIFIED evidence.

Do not edit application code, merge a PR, or move a Trello card to Done.
