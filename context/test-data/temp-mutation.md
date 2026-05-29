# Temporary Data Mutation

## When to use

When a scenario requires a specific data condition that doesn't currently exist in the test environment (e.g. an attorney with no team memberships, a case with no handling attorney, a feature flag in a particular state), and the condition can be constructed by temporarily modifying test environment settings.

## Allowed mutations

The following mutations are permitted during a test run, provided they are immediately restored after the scenario completes:

- **Team membership**: add or remove a user from a team in Settings → Teams to simulate "attorney has groups" vs "attorney has no groups" conditions.
- **Team toggle**: enable or disable the teams toggle in Settings → Teams to simulate firms with/without `limit_case_visibility`.
- **Feature flags**: enable or disable flags via localStorage override (standard pre-flight procedure).

## Required procedure

1. **Before mutating**: screenshot the current state as evidence of the original configuration.
2. **Mutate**: make the minimum change necessary to satisfy the scenario's Given condition.
3. **Run the scenario**.
4. **Restore immediately after**: revert the mutation before moving to the next scenario. Do not defer restoration to end-of-run.
5. **Log in trace**: write a `{"event":"data_mutation","action":"<what changed>","original":"<original state>","ts":"..."}` entry to `trace.jsonl` before the mutation, and a `{"event":"data_restore","action":"<what restored>","ts":"..."}` entry after restoration.

## Example (ECO-1526 — attorney with no group memberships)

- **Condition needed**: handling attorney exists in the firm but belongs to no teams.
- **Mutation**: open Settings → Teams → Test C → Edit → remove `firm admin` from Users → OK.
- **After scenario**: re-open Test C → Edit → add `firm admin` back → OK. Verify Test C shows (1) member.

## Hard rule: never skip without asking

If a scenario's data condition cannot be constructed (mutation is too risky, restoration is uncertain, or the condition requires data that doesn't exist at all), **do not silently skip the scenario**. Instead:

1. Pause execution.
2. Present the blocker to the user: what condition is needed, what was attempted, why it can't be constructed.
3. Ask the user to choose: (a) skip this scenario permanently, (b) defer to a future run, or (c) suggest an alternative way to construct the data.

Silent skips are forbidden — they create false confidence that coverage is complete.
