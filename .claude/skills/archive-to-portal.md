---
name: archive-to-portal
description: Manually archive a passing test from a run's artifacts to the portal-ui-automation repo. Usage `/archive-to-portal <run-id>/<unit-id>`. Copies 03-spec.md and trace.jsonl into portal's .claude/incoming/ directory so the portal add-test pipeline can generate properly-structured Playwright code. Never auto-pushes — the user triggers add-test themselves.
---

# /archive-to-portal

You are orchestrating a one-shot handoff from this repo's `artifacts/` to the portal-ui-automation repo's `add-test` pipeline.

## Natural language triggers

The user may invoke this skill with natural language instead of the slash command. Recognized patterns:
- "推送 XXX 到 playwright" / "把 XXX 推给 playwright" / "归档到 playwright"
- "archive XXX to portal" / "ship XXX to playwright"
- "automation XXX" / "自动化 XXX"

When the user names a ticket ID (e.g. "自动化 DOC-3144", "automation SUP-7152"), scan `artifacts/` for the most recent run whose directory name contains that ticket ID, then derive the unit-id from the run's `02-triage.json`. If multiple units exist or no matching run is found, ask the user to clarify before proceeding.

## Argument

`<run-id>/<unit-id>` — e.g. `2026-05-07_1430_SUP-7152/unit-1`

If missing or malformed, ask the user. Do not guess.

## Pre-flight

Before doing anything, sanity check:

1. `artifacts/<run-id>/03-spec-<unit-id>.md` exists — this is the primary input.
2. `artifacts/<run-id>/04-run-<unit-id>/trace.jsonl` exists.
3. `artifacts/<run-id>/04-run-<unit-id>/result.json` exists and contains `"passed_primary": true`. If not, refuse — the user can pass `--force` to override (surface a warning if they do).
4. `$PLAYWRIGHT_REPO_PATH` is set and points to a git repo with a `.claude/` directory.

If any check fails, print a clear error and stop.

## Workflow

1. Announce: "Handing off `<unit-id>` spec to portal repo at `$PLAYWRIGHT_REPO_PATH`"

2. Create the incoming directory if it doesn't exist:
   ```bash
   mkdir -p "$PLAYWRIGHT_REPO_PATH/.claude/incoming"
   ```

3. Copy the spec and trace:
   ```bash
   # Primary: structured spec for test-analyst fast-path
   cp artifacts/<run-id>/03-spec-<unit-id>.md \
      "$PLAYWRIGHT_REPO_PATH/.claude/incoming/spec-<run-id>-<unit-id>.md"

   # Execution record: selector + action details for add-test to reference
   cp "artifacts/<run-id>/04-run-<unit-id>/trace.jsonl" \
      "$PLAYWRIGHT_REPO_PATH/.claude/incoming/trace-<run-id>-<unit-id>.jsonl"
   ```

4. Tell the user:
   ```
   ✅ Spec handed off to portal repo.

   Files written to $PLAYWRIGHT_REPO_PATH/.claude/incoming/:
     - spec-<run-id>-<unit-id>.md          ← Requirement Spec (primary input)
     - trace-<run-id>-<unit-id>.jsonl      ← Executor trace (selector reference)

   Next step — in the portal-ui-automation repo, run:
     /add-test --from-spec .claude/incoming/spec-<run-id>-<unit-id>.md
   ```

## Hard rules

- **Manual only.** Never invoked automatically by `/test-tickets`.
- **Never push.** Never run `git push` or modify portal's tracked source files — only write to `.claude/incoming/`.
- **Never archive a failed run** unless `--force` was passed with a visible warning.
- **One unit per invocation.**

## Anti-patterns

- ❌ Inferring run-id/unit-id from "the most recent run" if not specified
- ❌ Touching any file in `$PLAYWRIGHT_REPO_PATH` outside of `.claude/incoming/`
- ❌ Running `npx playwright test` — the user does that after `add-test` generates the code
- ❌ Generating or adapting Playwright code yourself — that is the portal's `add-test` pipeline's job
