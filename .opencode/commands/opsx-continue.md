---
description: Continue an OpenSpec change by completing its next missing planning artifact.
agent: orca
---

Use the `openspec-workflow` skill to continue an existing change.

1. Run `openspec list --json` when `$ARGUMENTS` does not identify a change.
2. Run `openspec status --change "<change>" --json`.
3. Read all completed dependency artifacts and the instructions for the next ready artifact.
4. Ask the user when product intent, scope, acceptance criteria, or validation is ambiguous.
5. Create only the next planning artifact, then re-check status.
6. Stop when the change is implementation-ready or when a decision is required.

Do not implement application code in this command.
