# feature-caseloads

**Flag key:** `feature-caseloads`
**Gates:** Left Nav Caseloads entry — the `/caseloads/:id` route and the entire Caseloads UI module (`src/packages/app-v2/caseload/`)

## When to require this flag

Enable `feature-caseloads` whenever:
- The ticket mentions "caseload", "caseloads", "Case Tracker", or "saved view"
- Any changed file lives under `src/packages/app-v2/caseload/`
- The PR touches `packages/agent-runner/src/tools/caseloads/` or `src/api/routes/case-fields.ts`

## What it controls

Without this flag, the Caseloads tab in the left navigation rail shows **"Caseloads (Under Renovation)"** and is disabled — the route `/caseloads/:id` is unreachable from the UI. The entire Caseloads surface (roster, case peek, case details page, column manager, scope editor) is silently untestable if this flag is off.

Turning it on reveals the full Caseloads entry in the nav and allows navigation to `/caseloads/:id`.

## Notes

- This flag is independent of `feature-case-agent`. Both can be on simultaneously — the Case Agent chat within a caseload context also requires `feature-case-agent`.
- The `/cases/:id/details` route (CaseAttributesPage) may also be gated — verify by navigation when `feature-caseloads` is on.
- Toggle via `/toggle-feature-flag --flag feature-caseloads on` before starting any Caseloads test scenario.
