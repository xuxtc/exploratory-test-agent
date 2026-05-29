---
name: sync-test-cases
description: Manually sync test cases from a completed exploratory-test run into Google Sheets. Usage `/sync-test-cases <run-id>[/<unit-id>]`. Reads result.json + spec sidecar to build structured test cases from actual executed scenarios, then calls test-case-generator-agent/sync.py --from-run. Never auto-invoked — the user must trigger this explicitly after reviewing results.
---

# /sync-test-cases

You are syncing executed test scenarios from an exploratory-test run into the shared Google Sheets test case library.

## Argument

`<run-id>[/<unit-id>]` — e.g. `2026-05-07_1430_SUP-7152` (all units) or `2026-05-07_1430_SUP-7152/unit-1` (one unit).

If missing or malformed, ask the user. Do not guess or infer from "the most recent run".

Natural language triggers: "固化用例", "形成测试用例", "sync test cases", "把用例写进 sheet", "固化这次测试" — treat these as `/sync-test-cases <run-id>` when a run-id is mentioned in context, otherwise ask for the run-id first.

## Pre-flight

Before calling the script, verify:

1. `artifacts/<run-id>/` exists.
2. For each unit being synced: `artifacts/<run-id>/04-run-<unit-id>/result.json` exists.
3. Each targeted `result.json` has `"passed_primary": true`. If not, refuse and print:
   > Unit `<unit-id>` did not pass primary scenarios (`passed_primary: false`). Only passing runs produce reliable test cases. Pass `--force` to override.
   If the user passes `--force`, surface a warning but proceed.
4. `artifacts/<run-id>/03-spec-<unit-id>.json` exists for each unit (needed for Given/precondition data).

If any check fails (and `--force` was not passed), stop. Do not proceed.

## Workflow

1. Announce: "Syncing test cases from run `<run-id>` into Google Sheets."
2. For each targeted unit, collect the artifact paths:
   - Spec sidecar: `artifacts/<run-id>/03-spec-<unit-id>.json`
   - Result: `artifacts/<run-id>/04-run-<unit-id>/result.json`
3. Call the sync script in `--from-run` mode:
   ```bash
   cd ../test-case-generator-agent && python3 sync.py --from-run <absolute-path-to-artifacts-run-dir> [--unit <unit-id>] [--yes]
   ```
   - Pass `--unit` only when a specific unit was requested. Omit it to sync all units in the run.
   - Pass `--yes` only if the user explicitly said "skip confirmation" or `-y` in their trigger.
4. The script handles deduplication and prints a diff preview (NEW / UPDATE / SKIP) then waits for confirmation — do not bypass this unless `--yes` was requested.
5. Surface the script's output verbatim. Do not paraphrase case IDs, sheet names, or row counts.

## Hard rules

- **Manual only.** Never invoke this from `/test-tickets` automatically.
- **Never sync a failed run** (unless `--force`).
- **One run per invocation.** Don't batch multiple run-ids; each sync is a reviewable unit.
- **Never call `sync.py` with ticket IDs in `--from-run` mode.** The two modes are mutually exclusive — `--from-run` derives everything from the artifacts; passing ticket IDs alongside it is an error.

## Anti-patterns

- ❌ Inferring the run-id from "most recent run" when the user didn't specify it
- ❌ Passing `--yes` when the user didn't ask to skip confirmation
- ❌ Syncing failed units silently (status != pass)
- ❌ Running this during an active `/test-tickets` session (`.active` marker exists)
