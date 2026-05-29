# Rule: prod-internal-feature-flag-mgmt-skip

## When this rule applies

A ticket requires **operating the Feature Flag management UI** (Settings → Feature Flag → Feature Flag Toggles / User Level Feature Flags) using an `internal` account **on the `prod` environment**.

This rule applies when **all three conditions** are true:

1. **Env is `prod`** (not `stg`, not `prod-ca`).
2. **User role is `internal`** — the test requires an internal admin account to perform the operation.
3. **The core test action is Feature Flag management** — i.e. the scenarios require adding, removing, enabling, or disabling feature flags for users or roles via the admin Feature Flag UI.

### How to detect this during triage

Signal in the ticket or PR that triggers this rule:

- Ticket description or AC mentions "Feature Flag", "coffee_cup_flags", "Feature Flag Toggles", "User Level Feature Flags", or "Settings → Feature Flag"
- PR diff touches `FeatureFlagStore.ts`, `FeatureFlagsView`, or similar admin-only flag management surfaces
- The only way to construct the test's Given-state is through the admin Feature Flag management UI
- `user_role` inferred as `internal` primarily because Feature Flag management access is required

### What does NOT trigger this rule

- The ticket requires **enabling a feature flag as a precondition** (via `/toggle-feature-flag` localStorage override) — that is a test setup step, not Feature Flag management testing.
- The ticket's primary test surface is something other than the Feature Flag UI, and `internal` is needed for a different reason (e.g. admin dashboard unrelated to flags).
- The env is `stg` — this rule is prod-only. Feature Flag management testing on staging is allowed.

## What it controls

`test-triage` must skip the ticket and record it in the `skipped` array with:

```json
{
  "rule": "deterministic",
  "confidence": "high",
  "reason": "prod-internal-feature-flag-mgmt-skip: test requires internal account to operate Feature Flag management UI on prod — internal account has overly broad permissions on prod and must not be used for this purpose"
}
```

## Linear comment requirement

`linear-reporter` MUST post a comment on the ticket that:

1. States the ticket was evaluated and skipped.
2. Explains the reason: Feature Flag management testing on prod requires an internal account whose permissions are too broad for safe prod operation.
3. Recommends re-running on `stg` instead.

Template:

> **Test agent — skipped (prod internal Feature Flag management)**
>
> This ticket was evaluated by the test agent and skipped from E2E test coverage on prod.
>
> **Reason:** The test scenarios require an `internal` admin account to operate the Feature Flag management UI (Settings → Feature Flag) on the `prod` environment. The internal account carries overly broad permissions on prod — it has cross-company read access and is not safe to use for interactive testing on the production environment.
>
> **Recommendation:** Re-run this ticket with `--env=stg` to test Feature Flag management behavior on staging, where the internal account can be used safely.
>
> _Run: `<run-id>` · Evaluated by test-triage_

## Known interactions

- This rule is **deterministic** — it fires whenever all three conditions above are met, before LLM judgment.
- It does not apply when the ticket can be tested on `stg` instead; the skip message explicitly directs the user to re-run with `--env=stg`.
- It does not conflict with the production safety rules in CLAUDE.md — those govern write operations; this rule governs test feasibility under account permission constraints.
