---
name: toggle-feature-flag
description: Enable or disable a Supio Portal feature flag for a specific CDT session by calling the shared set-feature-flags.ts script. Usage `/toggle-feature-flag --flag <name> on|off [--session <session_id>]`. The session_id must match the unit's session_id to avoid cross-session interference in concurrent runs.
---

# /toggle-feature-flag

Calls the shared `scripts/set-feature-flags.ts` script (repo root) to toggle a Portal feature flag in the specified CDT session via the chrome-proxy HTTP sidecar.

## Why this skill exists

Feature flag toggling is a shared operation used by both exploratory-test-agent and regression-agent. The shared script at `scripts/set-feature-flags.ts` is the single implementation — this skill is the exploratory-test-agent's entry point to it.

## Args

- `--flag <name>` — required. The flag string as it appears in `localStorage.enabledFeatureFlags`, e.g. `feature-case-agent`.
- `on` / `off` — required. Desired end state.
- `--session <session_id>` — required in concurrent runs. Must match the unit's `session_id` (e.g. `unit-1`). Defaults to `default` if omitted, which is only safe for single-session usage.

Example:

```
/toggle-feature-flag --flag feature-case-agent on --session unit-1
/toggle-feature-flag --flag feature-case-agent off --session unit-2
```

## Pre-flight

1. A browser page must already be open on the Portal for the target session. If not, fail immediately with `no logged-in Portal page found for session <session_id>`.
2. Confirm the chrome-proxy sidecar is reachable: `curl -s http://localhost:9223/call` must respond (not connection refused).

## Workflow

Run the shared script from the repo root:

```bash
npx ts-node --project scripts/tsconfig.json --transpile-only scripts/set-feature-flags.ts \
  --flags=<name> \
  --action=<on|off> \
  --session=<session_id>
```

The script writes to `localStorage.enabledFeatureFlags` in the specified CDT session and reloads the page. Each `session_id` is an isolated Chrome instance — flags set in `unit-1` do not affect `unit-2`.

**Wait** for the page to finish loading after the script completes before proceeding.

**Verify** by reading localStorage in the same session:

```bash
curl -s http://localhost:9223/call -X POST -H "Content-Type: application/json" \
  -d '{"tool":"evaluate_script","arguments":{"function":"() => localStorage.getItem(\"enabledFeatureFlags\")"},"session_id":"<session_id>"}'
```

Confirm the flag is present (on) or absent (off).

Return a one-line confirmation to the caller:

```
toggle-feature-flag: 'feature-case-agent' → on  (session=unit-1, localStorage: applied, page reloaded)
toggle-feature-flag: 'feature-case-agent' → off  (session=unit-2, localStorage: removed, page reloaded)
```

## Trace entry

Emit one trace entry to `trace.jsonl` after success:

```json
{
  "ts": "<ISO-8601>",
  "event": "feature_flag_preflight",
  "flag": "<name>",
  "desired": "on|off",
  "session_id": "<session_id>",
  "outcome": "on|off"
}
```

## Error states

| Situation | Action |
|---|---|
| No Portal page open for session | Abort: `no logged-in Portal page found for session <session_id>` |
| Sidecar not reachable | Abort: `chrome-proxy sidecar not running on localhost:9223 — reload VS Code to restart MCP` |
| Flag already in desired state | Skip (no-op). Return `toggle-feature-flag: '<name>' already <on|off> in session <session_id>, no change.` |

## What this skill does NOT do

- Does not change the backend's `enabled_feature_flags` for the account — only the in-browser localStorage override.
- Does not remember flag state across sessions. Each new browser session starts with whatever `localStorage` the Portal sets on login.
- Does not validate that the flag name is spelled correctly — the caller is responsible for the exact flag string (see `context/feature-flags/` for known flags).
