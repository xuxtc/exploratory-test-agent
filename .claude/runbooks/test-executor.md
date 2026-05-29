---
name: test-executor
mode: in-context-runbook
description: Runbook the ORCHESTRATOR follows in the main session to execute a Requirement Spec end-to-end against a real browser using Chrome DevTools MCP. NOT a sub-agent. Drives Chrome step-by-step, captures screenshots and a trace, and evaluates each scenario's Then-clauses.
---

# test-executor (in-context runbook)

The orchestrator (the main `/test-tickets` session) reads this file and follows it. **Do not** invoke this via `Agent({subagent_type: "test-executor"})` — sub-agents don't receive deferred MCP tool schemas, so a spawned executor can't actually call any `mcp__chrome-devtools__*` tool. Driving Chrome from the main session is the only configuration that works on Claude Code (extension v2.1.133, CLI 2.1.25). If a future release fixes deferred-tool propagation, verify with a probe spawn before reverting.

## Non-negotiable rules — never skip, never shortcut

These rules are not guidelines. Violating any one of them produces a run that cannot be trusted:

1. **Screenshot pre-flight before every `take_screenshot`** — run `evaluate_script` to confirm the key evidence text is visible in `document.body.innerText`. If it is not, fix the page first. A screenshot on the wrong page is worse than no screenshot.
2. **Screenshot immediately after each scenario** — while the page is still in the post-action state. Never defer to after the scenario loop.
3. **`scenario_pass` / `scenario_fail` trace entry only after the screenshot file exists on disk.** No screenshot = no trace entry = do not advance to the next scenario.
4. **Before writing `result.json`, run `ls screenshots/`** — enumerate every file in the directory, then verify each one is referenced in at least one scenario's `screenshot` field or in `screenshot_picks_for_comment`. Any unaccounted file must be added. Never construct `screenshot_picks_for_comment` from memory.
5. **`session_id` on every `mcp__chrome-devtools__*` call** — use the unit's `unit_id` (e.g. `"unit-1"`). Never omit it.
6. **Never kill `proxy_server.py`** — only kill child `chrome-devtools-mcp` processes. **Never use a global `pkill -f "chrome-devtools-mcp"`** — it kills all sessions including those belonging to other CC windows running concurrent tests. Always scope the pkill to this unit's profile: `pkill -f "chrome-proxy-profile-<unit_id>"`.
7. **One Chrome process per unit — no exceptions.** Each `session_id` spawns a separate OS-level Chrome browser process. Using a different `session_id` mid-run (even accidentally) opens a new browser window that is never cleaned up. The `session_id` is fixed at the start of Phase 5 as `"<unit_id>"` (e.g. `"unit-1"`) and must not change for any reason — not for `/switch-account`, not for retries, not for "fresh start". Violating this rule is the direct cause of multiple stray browser windows accumulating on the operator's machine and subsequent `take_screenshot` timeouts from CDP compositor contention.

If you find yourself about to skip any of these (e.g. "the page state is obvious, I don't need to verify"), stop. Do the check. The rules exist because skipping them has already caused silent failures in prior runs.

**First step in Phase 5 — kill stale Chrome MCP processes for this session before loading tools.**

A leftover `chrome-devtools-mcp` *child* process from a prior run of the **same session** holds a Chrome profile lock and will block subsequent MCP tool calls. Kill only the child processes belonging to this unit's `session_id` — **never do a global pkill** — because other CC windows may be running concurrent tests with their own sessions and a global pkill would kill their Chrome instances mid-run.

**Do NOT kill `proxy_server.py`** — it is the long-lived MCP proxy managed by Claude Code's MCP layer; killing it severs all chrome-devtools tool calls for the entire session.

```bash
# Step 1: Kill stale Chrome process for THIS unit only
pkill -f "chrome-proxy-profile-<unit_id>" 2>/dev/null
sleep 1
echo "Chrome MCP child process for <unit_id> cleared"

# Step 2: Check for any OTHER stale chrome-proxy-profile-* processes
# (left over from previous runs or aborted sessions on this machine)
pgrep -la "chrome-proxy-profile" 2>/dev/null
# If any processes appear above that do NOT belong to a concurrently running
# CC window, kill them now:
#   pkill -f "chrome-proxy-profile-<other_unit_id>"
# If you are unsure whether a process belongs to another live CC window,
# leave it — do not kill it.
```

**After the cleanup, confirm only one Chrome process will be used for this entire unit.** The `session_id` is locked to `"<unit_id>"` from this point forward — it must not change for any reason (not for `/switch-account`, not for retries, not for re-logins). Opening a second `session_id` spawns a second OS-level browser window that is never automatically cleaned up and causes `take_screenshot` timeouts via CDP compositor contention.

**`session_id` is required on every chrome-devtools tool call.** The proxy routes each call to the Chrome instance associated with that `session_id`. Use `session_id: "<unit_id>"` (e.g. `"unit-1"`, `"unit-2"`) — one consistent value per unit across the entire executor run. Omitting `session_id` falls back to `"default"`, which is shared and will collide with other units running in parallel. Always pass it explicitly.

Then load the chrome-devtools tools into context:
```
ToolSearch({query: "select:mcp__chrome-devtools__navigate_page,mcp__chrome-devtools__new_page,mcp__chrome-devtools__list_pages,mcp__chrome-devtools__select_page,mcp__chrome-devtools__resize_page,mcp__chrome-devtools__take_screenshot,mcp__chrome-devtools__take_snapshot,mcp__chrome-devtools__click,mcp__chrome-devtools__fill,mcp__chrome-devtools__fill_form,mcp__chrome-devtools__evaluate_script,mcp__chrome-devtools__wait_for,mcp__chrome-devtools__press_key,mcp__chrome-devtools__type_text,mcp__chrome-devtools__list_console_messages,mcp__chrome-devtools__list_network_requests,mcp__chrome-devtools__upload_file,mcp__chrome-devtools__handle_dialog,mcp__chrome-devtools__hover", max_results: 25})
```
Add more via subsequent `ToolSearch` if you need them (`get_console_message`, `get_network_request`, etc.).

## Inputs / Outputs

The executor is invoked **once per ticket** (not once per unit). The orchestrator calls it sequentially for each ticket in the unit.

**Inputs**
- `artifacts/<run-id>/03-spec-<unit_id>-<ticket_id>.json` — the spec sidecar for this ticket (contract; do not parse the .md sibling).
- `config/env.stg.json` (stg), `config/env.prod.json` (prod), or `config/env.ca.json` (prod-ca) — URLs + creds per env per role.
- `artifacts/<run-id>/02b-data-plan.json` (optional) — the planner's case decision for this unit (shared across all tickets in the unit).

**Outputs under `artifacts/<run-id>/04-run-<unit_id>-<ticket_id>/`**
- `trace.jsonl` — **mandatory**. One JSON object per step. Schema: `schemas/run-trace.schema.json`. The schema field is `event`, never `t`. Write the first entry (`run_start`) before any browser action. Append every subsequent step immediately as it happens — do not batch. If `trace.jsonl` cannot be written, abort the run.
- `screenshots/` — PNGs at named checkpoints + every failure.
- `result.json` — per-scenario verdict. Schema: `schemas/run-result.schema.json`.

Each ticket in a unit gets its own isolated run directory (`04-run-<unit_id>-<ticket_id>/`). Browser auth may be reused across tickets in the same unit (same session, same login), but trace, screenshots, and result.json are always per-ticket.

## Hard rules

### Production safety for internal accounts (highest priority)

This section enforces the project-level rule of the same name in `CLAUDE.md`. When `env=prod` AND `user_role=internal`, the executor must:

1. **Capture the test-company identity at login.** Right after `login_as`, run `evaluate_script` to read the current company id / slug from the URL or from the `me` GraphQL response, and hold it as `test_company_id` for the run. Trace `{"event":"company_pin","company_id":"...","source":"url|graphql"}`.
2. **Block any company-switch UI.** Do not click company-switcher controls, "switch to" links, or admin-impersonate affordances. Do not navigate to `?company_id=<other>`, `/companies/<other>/...`, or any URL whose company segment differs from `test_company_id`.
3. **Pre-write company check.** Before every state-mutating action (click that submits a form, file upload, archive, delete, field edit, comment, status change), assert that `location.href` still belongs to `test_company_id`. If the page has drifted to a different company, abort the scenario, mark FAIL with reason `prod-internal safety: drifted off test company to <observed>`, screenshot, and stop the unit. Trace `{"event":"prod_internal_safety_block","gate":"company","observed":"...","expected":"..."}`.
4. **Pre-write deqtest_ check.** Inside the test company, before every state-mutating action against an existing case, read the current case's display name (header text, breadcrumb, or `evaluate_script` against the case-detail container) and assert it starts with `deqtest_`. If not, abort the scenario, mark FAIL with reason `prod-internal safety: write to non-deqtest case '<observed-name>' blocked`, screenshot, and stop the unit. Trace `{"event":"prod_internal_safety_block","gate":"deqtest_prefix","observed":"<name>"}`.
5. **/create-case exemption.** At the moment of clicking the Create button on `/create-case`, the case does not yet exist — the gate that applies there is "the Case Name field's value starts with `deqtest_`". Verify that before clicking Create. Post-create, the new case naturally satisfies the prefix gate for any subsequent scenarios.
6. **No override path.** Do not prompt the user to bypass these checks. Do not silently skip. If a spec or planner instruction would force a violation, the spec is wrong — record an `open_question` finding and do not execute.

These checks are skipped when `user_role=external` (the external test account has no cross-company privileges and the test tenant is isolated, per `env.prod.json`'s prod block). They are also skipped on `env=stg`.

### Credentials

- Select config file by env: `stg` → `env.stg.json`, `prod` → `env.prod.json`, `prod-ca` → `env.ca.json`.
- Read `accounts[<role>]` array. If `user_role` from triage is `"team"`, resolve to `accounts["external"]` filtered by `tags: ["teams"]` (first match).
- Read the config once at run start; hold in agent-local memory; use only for login.
- **Never** write the password into trace, screenshots (mask password fields before screenshotting), result.json, or chat.
- If no matching account found for the requested role+tag, abort with a clear message — do not silently fall back to another account.

### Mid-run role switching

When a scenario's `user_role` differs from the unit's default:
1. Group same-role scenarios first; run role-switching scenarios in a tail group.
2. Invoke the **`/switch-account` skill** with `--role <target>`. Don't roll your own logout/login flow — earlier runs wasted 2-3 minutes per switch; the skill encodes the working path. See `.claude/skills/switch-account.md`.
3. After the role-switching scenario, invoke `/switch-account --role <original>` to restore the unit's default.
4. If creds are `null` for the target role, mark the scenario FAIL with `fail_reason: "<role> credentials not provisioned for env=<env>; AC requires <role> role"`. **Do not** mark `skipped_per_spec` — a missing role is a real test gap.
5. Record each switch as a `login_as` trace entry with the new account's email (returned by the skill).

### Fresh AI session by default

For chat / AI-session UX (case-agent, mailroom-chat, drafting-agent), **create a new session at scenario start** unless the spec's `data_setup` names a specific existing session as a fixture. Reusing the top-of-sidebar session is forbidden — non-reproducible, leaks state across runs, may have been created on the old code. Send a prompt known to produce the needed citations/state, wait for the reply, then exercise the scenario.

### Browser driving rules

**Page load waiting (slow target site).** Default `navigate_page` timeout (10s) often fires before the page is ready, returning an error while loading continues. Treat every navigation/click-that-changes-page as: (1) trigger, (2) confirm load — `wait_for` on text you expect on the post-load page (e.g. `["Log in"]` for login, the user's display name for a logged-in dashboard), or fall back to `evaluate_script` returning `{readyState, url, title}`. Pass explicit `timeout: 30000` on slow pages. **A `navigate_page` timeout is not a failure** — check `list_pages`/`evaluate_script` first; only treat it as failure if `wait_for` *also* times out. Never screenshot or assert before confirming load — blank-background screenshots are always a workflow bug.

**`take_screenshot` rules — prevent timeout and missing evidence.**

1. **Always confirm page stability before calling `take_screenshot`.** The call sequence is: navigate/action → `wait_for` (confirm load) → `take_screenshot`. Never call `take_screenshot` immediately after `navigate_page` without a `wait_for` in between — the Chrome DevTools Protocol screenshot command hangs when the page is still loading and triggers an MCP-layer timeout (~30s).
2. **Avoid `fullPage: true` on data-heavy pages.** Pages with long lists (Medical Chronology, Ledger, Case Files) require Chrome to scroll-render the entire page before compositing — this routinely exceeds the MCP timeout. Use the default viewport screenshot instead; if the relevant element is below the fold, scroll to it first with `evaluate_script("document.querySelector('...').scrollIntoView()")` then screenshot.
3. **Retry once on timeout.** If `take_screenshot` returns a timeout error, wait 2s (`evaluate_script("await new Promise(r=>setTimeout(r,2000))")`) and retry exactly once. If the retry also fails, record the failure in `trace.jsonl` as `{"event":"screenshot_failed","reason":"timeout after retry","scenario_id":N}`, set `screenshot_omit_reason` on the scenario, and continue — do not abort the run.
4. **Kill stale Chrome MCP processes for this session at run start** (already required at the top of this runbook). Use `pkill -f "chrome-proxy-profile-<unit_id>"` — never a global pkill, which would kill concurrent runs in other CC windows.

**Reloads are evidence-destroying.** Reloading erases live-update bugs: the timeline that didn't push events when extraction completed, the file-status badge that didn't advance, the Case Activity card that didn't refresh. If you reload "to verify the next step", you can't tell whether data appeared because of the reload or because the app updated live. Rules:
1. **Don't reload** unless (a) the spec or PR explicitly names a reload as a When step (testing localStorage/cookie/DB persistence specifically), or (b) the page is in a wedged error state.
2. **Before any spec-required reload, run a live-update sanity sweep**: `evaluate_script` snapshot the live-data widget's count/state and compare to what the network response said it should be. Mismatches go in `result.json.live_update_findings[]` as `[Warning]` items, not as scenario PASS/FAIL.
3. **Prefer in-page actions over reloads**: tab-switch, scroll-to-fetch, `evaluate_script` polling for ~10s.
4. **Order matters**: when a spec needs both observation and reload, observe *first*, then reload.

(Original example: SUP-7623 — close-persists-across-reload PASSed, but the executor missed that timeline events didn't auto-populate as extraction completed; only after the close-and-reload in scenario 4 did events appear. That's a finding worth reporting; a premature reload would have hidden it.)

**Server-side processing waits (Supio case parsing).** Uploading files **no longer triggers extraction automatically**. After `/create-case` completes, the executor must explicitly ask the Case Agent to generate the timeline before polling. Skipping this step causes the case to sit with "No events found" indefinitely.

**Pre-poll step (mandatory for `create_fresh` cases):** After `/create-case` returns and before entering the polling loop, navigate to the case and send **"generate timeline"** to the Case Agent chat. Wait for the Agent to reply with a "Timeline generated" or "events committed" confirmation before starting the poll.

```
1. Navigate to /cases/<id>/medical-chronology (or any case tab).
2. Click the Agent chat input and type "generate timeline", then send.
3. Wait for Agent reply confirming timeline generation (≤60s).
4. Then enter the polling loop below.
```

The canonical signal for extraction completion is the **Medical Chronology tab** (`/cases/<id>/medical-chronology`) — if any timeline events have been extracted, they appear there.

Polling procedure:
1. Navigate to `/cases/<id>/medical-chronology`.
2. `wait_for(["No events found", "Updating your timeline", "View", "new files", "Incident", "Treatment"], timeout=15000)`.
3. If the page shows **"Updating your timeline — Extracting N timeline files"**: extraction is in progress. Yield via `ScheduleWakeup` for 90-120s and re-poll from step 1.
4. If the page shows **"No events found"** (without the "Updating" banner) and files are in CASE FILES: yield 90-120s and re-poll. **Do NOT send "generate timeline" again** — a second invocation during an in-progress extraction may create duplicate events.
5. If events are visible (dates, provider names, event descriptions) or a **"View N new files"** button appears: extraction complete ✅.
6. Cap total wait at 20min; if still no events, proceed and note "extraction pending" in `result.json`.

**Important:** Do NOT use the Events tab (`/cases/<id>/events`) to check extraction status — that tab shows case-level events (created, updated, etc.), not extracted medical timeline events. Always use `/medical-chronology`.

**Do not use `/api/v1/cases/<id>/event-count`** — verified to always return `event_count: 0` even when events exist on the page. Similarly, `/api/v1/chronology/<id>/legacy-events` returns `total: 0` in tests. Neither API is reliable as an extraction signal. Always use the Medical Chronology page directly. Never write a hardcoded `sleep 600s`.

**Fixture file paths.** chrome-devtools MCP only reads files inside its workspace roots. Anything under `~/Downloads`, `/tmp`, `~/Desktop`, etc. will be refused with `Access denied: path ... is not within any of the workspace roots`. Fixtures downloaded by `get-fixture.py` land in `exploratory-test-agent/fixtures/cache/` which is inside the workspace root — use those paths directly with `upload_file`. Do not copy fixtures into `artifacts/` or `/tmp`.

**Drag-and-drop (dnd-kit).** The Chrome DevTools MCP accessibility-tree driver cannot trigger native `DragEvent` — dnd-kit explicitly blocks it. For any scenario requiring drag-reorder on a `@dnd-kit`-based component (signals: `aria-label="Drag to reorder"` handles, `roledescription="sortable"` rows), use the **PointerEvent simulation** technique documented in `context/browser-interactions/dnd-kit-drag.md`. That file contains the verified script, assertion checklist, and important notes (re-query handles after each drag, 300ms settle delay between consecutive drags).

### Known-unreliable interaction types — attempt rules

For each of the following, the executor must NOT exhaust all possible JS/fiber approaches. Apply the documented rule, mark the scenario, and move on. Human intervention is more productive than additional attempts.

**DS Radix Checkbox / Switch — 2 CDT MCP clicks, then blocked.**
When a `button[role="checkbox"]` or `button[role="switch"]` built with `@radix-ui/react-checkbox` or `@radix-ui/react-switch` does not change `data-state` after **2 CDT MCP `click` calls**, stop immediately. Do NOT proceed to JS `element.click()`, React fiber `onClick`, `__reactProps.onClick`, `onCheckedChange`, or Space key. Mark the scenario `fail` with:
```
fail_reason: "DS Radix [checkbox|switch] unresponsive to CDT MCP click (2 attempts) — manual verification required. Component is visible and not disabled; state did not change."
```
Take a screenshot showing the element in its unchecked/unset state before marking fail. See `context/browser-interactions/radix-checkbox.md` for background.

**AI-triggered tool-call UI — 1 prompt attempt, then blocked.**
When a scenario depends on the AI backend emitting a specific tool call (e.g. `present_file_tree`, `present_citation_card`) to render a UI widget, make **exactly 1 prompt attempt**. Wait as long as the AI needs to respond — do not impose a timeout. After the AI replies, check whether the widget appeared. If it did not, mark the scenario `fail` with:
```
fail_reason: "AI-triggered tool call not emitted after 1 attempt — manual verification required. AI responded but did not emit [tool-call-name]."
```
Do NOT retry with a rephrased prompt. Additional AI round-trips are almost never productive for probabilistic tool-call emission, and the extra wait time is the dominant cost. See `context/testing-scope/ai-agent-tool-call-ui.md` for the list of known tool-call UI components and the required session state to attempt them.

**Browser lifecycle.** Prefer a clean profile per run. After each scenario, reset to a clean state (navigate to env base URL or close+reopen the page) — scenarios must not leak state into each other. On unrecoverable error: final screenshot, write what you know to `result.json`, exit. No silent retry-forever.

### Feature flag pre-flight (run BEFORE any state-creating action)

Supio has a runtime flag-sync gap: backend `me.enabled_feature_flags` may include a flag, but the React store only honors it after a local override appears in `localStorage.enabledFeatureFlags`. Skipping pre-flight makes the UI render the *pre-feature* path and produces false-negative scenario failures.

For every flag in `Preconditions → Feature flags`:
1. **Write localStorage**:
   ```js
   () => {
     const have = (localStorage.getItem('enabledFeatureFlags') || '').split(',').filter(Boolean);
     const need = ['feature-foo']; // from spec
     localStorage.setItem('enabledFeatureFlags', Array.from(new Set([...have, ...need])).join(','));
     return localStorage.getItem('enabledFeatureFlags');
   }
   ```
   For `must_be_off`: remove the flag from the same string.
2. **Reload** with `navigate_page({type:"reload"})` and re-confirm load. The override is read on first paint; without a reload, gated UI sections won't appear.
3. **Trace entry per flag**: `{"event":"feature_flag_preflight","flag":"...","localStorage_before":[...],"localStorage_after":[...],"outcome":"on"}`.

**Pre-flight runs before *every* state-creating action**, not just scenarios. If `data_setup` creates a case/session/workspace via a feature-gated flow, the flag must be ON before that creation — backends commonly bind pipelines/features at create-time, and toggling after the object exists doesn't retroactively switch the pipeline. (Observed: a case created with `feature-ai-artifact-first` OFF was permanently bound to the legacy pipeline; only a re-created case under flag-ON saw the new UI.)

### Component identity verification (before the FIRST scenario)

The spec names an exact component identity (`data-testid`, accessible role+name, or unique class chain) taken from the PR diff. Before any scenario, prove that exact component is reachable. If you can't, *don't run scenarios yet* — verdicts will be meaningless.

Procedure:
1. Re-read the spec's Preconditions + first scenario's Given. Note the exact selector.
2. Navigate to the Given URL; wait for load.
3. `evaluate_script` to count nodes matching the selector. **Hold to the exact selector** — not a textual match like "popover whose header says Timeline Complete". Identical-looking siblings are common (LedgerFilePanel and TimelineGenerationPanel both can show "Timeline" in the right-bottom slot).
4. Three outcomes:
   - **Match ≥1**: proceed to the scenario loop.
   - **Zero, but spec says it should be visible**: NOT a scenario FAIL. Either you picked the wrong case (legacy vs AI-first) or a visibility gate is closed (`wasEverProcessing=false` etc.). Stop, reconcile (different case, construct missing state, or Open-questions note), resume only after match.
   - **Zero, and spec asserts hidden**: legitimate observation. Still verify the Given holds (so absence is *because* of the gate, not because the component was never in the tree).
5. Record one `component_identity_verified` trace entry: case id, selector, hit count, outcome.

(Why this matters: SUP-7623 didn't pin a `data-testid`, the executor saw a popover in the right region with "Timeline Complete" in it, ran four scenarios against `data-testid="snapshot-window"` instead of the actual `timeline-generation-panel`, reported three FAILs that were spec gaps. Pin the identity, then verify it lands.)

### Case fitness check (run alongside identity verification)

Many specs target a specific kind of case (AI-first vs legacy, MVA vs other, fresh vs ledger-enabled). Cheap signals:
- **AI-first vs legacy**: AI-first cases mount components from `src/packages/ai-artifact-first/...`. Presence of `data-testid="timeline-generation-panel"` *anywhere* on the timeline tab — even hidden — is a positive signal. Total absence after 5s suggests legacy.
- **Case state**: if spec says "in `extracting`", check the network log for `ai-first-timeline-generation-status` with that status. Don't infer from header text — header copy lags by a polling cycle.
- **Per-user gates**: if spec mentions `useEducationDismissal`, check `/api/v1/user-education-dismissals/<key>/dismissed`.

Wrong-kind case is the highest-cost bug: it produces a FAIL report that looks plausible but is meaningless. When in doubt, create a fresh case via `/create-case` rather than reuse an unfamiliar one.

### Scenario execution

For each scenario in spec order:
1. Set up the **Given** state (often: log in, navigate). Reuse auth across scenarios if safe.
2. Perform the **When** actions; trace each with before+after screenshots if the action mutates the page.
3. Evaluate each **Then** — one `assert` entry per Then, `outcome: pass|fail`. **Do not collapse multiple Thens into one assert.**
4. **Take the scenario screenshot NOW, before moving to the next scenario.** The page must still be in the post-action state showing the verdict. Do not defer screenshots to after the scenario loop — by then you will have navigated away and the evidence is gone.
5. Write the `scenario_pass` or `scenario_fail` trace entry **only after** the screenshot file exists on disk. No trace entry without a screenshot path.
6. If any `[primary]` Then fails: mark scenario failed, continue to the next scenario. Do not abort the whole run on a single primary failure.
7. Edge scenarios that fail are recorded but do not block report.

### Screenshot evidence — required for every active scenario, PASS or FAIL

Each scenario in `result.json` must include a `screenshot` field (relative path under `04-run-<unit_id>/`). **This field is mandatory for every scenario whose `status` is `pass` or `fail`. The only exception is `skipped_per_spec` — those scenarios must omit the field entirely.**

**Multiple scenarios may share one screenshot** when the same page state proves all of them (e.g. a single agent response that covers three assertions). In that case:
- All sharing scenarios must reference the same path in their `screenshot` field.
- `screenshot_picks_for_comment` must list that screenshot **once**, with a `title` that names every covered scenario: e.g. `"S1/S2/S4 — <short description>"` and a `caption` that explicitly states which scenarios it covers.
- Do not create duplicate entries in `screenshot_picks_for_comment` for the same file.

**If a screenshot file exists, it must be used — regardless of scenario status.** A `skipped_per_spec` scenario does not require a screenshot, but if one was taken (e.g. to prove the data_blocker is real), it must appear in `screenshot_picks_for_comment`. A screenshot sitting in the `screenshots/` directory but absent from `screenshot_picks_for_comment` is always a bug. Before writing `result.json`, check: for every file in `screenshots/`, is it referenced by at least one scenario's `screenshot` field or in `screenshot_picks_for_comment`? If not, add it.

**Screenshot pre-flight: verify content before calling `take_screenshot`.** Before every `take_screenshot` call, run `evaluate_script` to assert that the key evidence is actually visible in the DOM:

```js
// Example for an agent response scenario:
() => ({
  ok: document.body.innerText.includes('<unique phrase from agent reply>'),
  snippet: document.body.innerText.slice(0, 300)
})
```

If `ok` is `false`, the page is not showing the right state — do NOT call `take_screenshot`. Instead, fix the page first:
- If the chat pane is collapsed: navigate to `/`, click the session from the sidebar list, wait for the conversation to render, then re-run the pre-flight check.
- If on the wrong tab/page: navigate to the correct URL first.
- Only call `take_screenshot` after `ok` is `true`.

This check is not optional. A screenshot taken on the wrong page is worse than no screenshot — it silently passes validation while providing false evidence.

Three FAIL flavors:
- **Spec FAIL** (UI did the wrong thing): screenshot the post-action frame showing the wrong state.
- **Blocked-no-test-data FAIL**: screenshot the surface in a state that *proves* data is missing — the file list with the highest-event-count file visible (so reader sees "max=7, threshold needed >10"), the citation footer showing only Timeline-event entries (so reader sees "no ConversationFile here"). The picture must make the blocker self-evident.
- **Unreachable FAIL** (precondition can't be constructed): if there's nothing visible to photograph, omit `screenshot` AND set `screenshot_omit_reason` to a one-sentence explanation (e.g. `"requires internal role; external user never sees this surface"`). Also state the reason in `fail_reason`. Reporter renders the FAIL caption text-only. This is the only case where a `fail` scenario may omit `screenshot` — and `screenshot_omit_reason` must be present to pass schema validation.

When in doubt, take the screenshot. A picture proves the run happened; missing pictures invite the reader to assume the agent skipped the work.

## Timing log (fine-grained)

**Timing data is for local analysis only — it must never appear in Linear comments or any artifact that linear-reporter reads.**

The orchestrator writes phase-level entries; you write the **executor sub-phase entries** so a slow run can be broken down to the exact operation. All entries go to `artifacts/<run-id>/timing.log` (JSONL, one object per line, appended immediately — never batched).

```bash
echo '{"ts":"'$(date -u +%Y-%m-%dT%H:%M:%SZ)'","phase":"execute","event":"<event>","unit_id":"<unit_id>","ticket_id":"<ticket_id>","detail":"<optional>"}' >> artifacts/<run-id>/timing.log
```

The entries fall into four categories matching the four main time sinks in browser execution:

---

### Category A — Precondition setup

These record time spent *before* any scenario runs. They are almost always the largest block on a slow ticket.

| Moment | `event` | `detail` |
|--------|---------|---------|
| Before login (or first page action if session reused) | `login_start` | `"new_login"` or `"reused_session"` |
| After login confirmed (`wait_for` matched user display name) | `login_end` | email used |
| Before feature-flag pre-flight loop | `flag_preflight_start` | `"flags:<N>"` — count of flags to set |
| After all flags applied and page reloaded | `flag_preflight_end` | — |
| Before `/create-case` skill call | `case_create_start` | `"kind:<case_kind> fixtures:<N>"` |
| After case id written to `case_id.txt` | `case_create_end` | `"case_id:<id>"` |
| Before entering extraction polling loop | `extraction_poll_start` | `"case_id:<id>"` |
| Each yield while extraction is still in-progress | `extraction_poll_wait` | `"attempt:<N> waited_so_far_s:<seconds>"` — compute elapsed from `extraction_poll_start` ts |
| When extraction completes or 20-min cap reached | `extraction_poll_end` | `"outcome:complete"` or `"outcome:cap_reached"` |

---

### Category B — Scenario execution steps

One pair of entries per scenario — plus one entry per individual **When action** inside the scenario so you can see which browser operations were slow.

| Moment | `event` | `detail` |
|--------|---------|---------|
| Before scenario N begins (Given setup) | `scenario_start` | `"s<N>:<title>"` |
| Before each individual When action | `step` | `"s<N> step:<k> <verb> <target>"` — e.g. `"s2 step:1 click Upload button"`, `"s2 step:2 fill filename field"`, `"s2 step:3 wait_for extraction badge"` |
| After scenario N ends (all Then assertions evaluated) | `scenario_end` | `"s<N> verdict:<pass\|fail\|blocked>"` |

For `wait_for` calls that block for more than ~3 seconds, also log the duration:

| Moment | `event` | `detail` |
|--------|---------|---------|
| A `wait_for` that takes > 3 s | `wait` | `"s<N> step:<k> selector:<selector> waited_s:<seconds>"` |

---

### Category C — Execution path errors and rework

These entries record time **wasted** on wrong paths — the main source of unexplained duration in complex runs.

| Moment | `event` | `detail` |
|--------|---------|---------|
| Component identity check finds zero matches | `reconcile_start` | `"s<N> selector:<selector> case_id:<id> reason:component_miss"` |
| After reconcile resolves (new case selected or state constructed) | `reconcile_end` | `"s<N> resolution:<description>"` — e.g. `"switched to case 99831 (AI-first)"` |
| Case fitness check fails (wrong kind) | `reconcile_start` | `"s<N> reason:wrong_case_kind expected:<kind> observed:<kind>"` |
| After fitness reconcile | `reconcile_end` | `"s<N> resolution:<description>"` |
| Mid-scenario the Given state can't be constructed | `reconcile_start` | `"s<N> step:<k> reason:given_state_missing detail:<description>"` |
| After mid-scenario reconcile | `reconcile_end` | `"s<N> resolution:<description>"` |
| `/switch-account` invoked (role change mid-unit) | `role_switch` | `"from:<role> to:<role>"` |

Any `reconcile_start` without a corresponding `reconcile_end` means the executor gave up — log it as `reconcile_end` with `"resolution:aborted"`.

---

### Category D — Screenshot overhead

Screenshots are synchronous and can add up across a multi-scenario run.

| Moment | `event` | `detail` |
|--------|---------|---------|
| Before `take_screenshot` call | `screenshot_start` | `"s<N> file:<filename>"` |
| After screenshot written to disk | `screenshot_end` | `"s<N> file:<filename>"` |

---

Write every entry **immediately** as the event occurs. Do not batch at scenario-end or unit-end.

**These entries are read only by humans and by `/retro` — they never flow into `result.json`, `trace.jsonl`, `05-summary.md`, or Linear comments.**

## Workflow

0. **Export `TIMING_LOG` before any Bash command** so that all downstream scripts (`get-fixture.py` → `google-drive.py`) automatically write into the active run's timing.log without needing to resolve the run-id themselves:
   ```bash
   export TIMING_LOG="$AGENT_ROOT/artifacts/<run-id>/timing.log"
   ```
   This must be the very first Bash action in the executor. Substitute the actual `<run-id>`. Every subsequent `Bash` call in this runbook inherits this env var automatically.

1. Read `artifacts/<run-id>/03-spec-<unit_id>-<ticket_id>.json` (the contract for this ticket). Markdown sibling is human-only.
2. Verify env + role from sidecar `preconditions`. Load creds. Abort early on missing config.
3. Initialize Chrome DevTools MCP. Navigate to env base URL. **Reuse existing browser auth if a sibling ticket in the same unit was just executed** (check if already logged in before attempting login again).
4. **Write `run_start` trace entry immediately** — `{"event":"run_start","run_id":"...","unit_id":"...","ticket_id":"...","env":"...","user_role":"...","ts":"..."}`. Output goes to `artifacts/<run-id>/04-run-<unit_id>-<ticket_id>/trace.jsonl`. This is the first write; if it fails, abort before touching the browser.
5. Log in if not already authenticated. Write `login_start` (Category A) before the login action and `login_end` after `wait_for` confirms the session. `login_as` trace entry.
6. **Feature flag pre-flight** for every flag in `preconditions.feature_flags`. Write `flag_preflight_start` (Category A) before the loop and `flag_preflight_end` after all flags are set and the page is reloaded.
7. **Resolve the case per the data plan.** If `02b-data-plan.json` exists, find the `case_groups[]` entry containing your `unit_id`:
   - Sibling ticket already created the case this run? Read `case-group-<id>/case_id.txt` and **reuse** (trace `{"event":"case_reuse","case_id":"<N>"}`).
   - `case_decision: create_fresh`? Write `case_create_start` (Category A), call `/create-case` skill with the plan's `case_kind` and each fixture in `fixtures_needed` via `--add <name>`. Write the new case-id to `case-group-<id>/case_id.txt`. Write `case_create_end` (Category A). Trace `{"event":"case_create",...}`.
   - `case_decision: reuse_existing`? Use `case_id` from the plan. Write to `case_id.txt` for symmetry. Trace `{"event":"case_resolve","source":"data-plan-reuse"}`.
   - `case_decision: blocked_no_fixture`? Write `result.json` with every active scenario `❌` and `fail_reason` from the plan's `fixture_gap`. Skip the scenario loop.
   - **Never override the plan unilaterally.** If you think the plan is wrong, surface it in `result.json.live_update_findings[]`; don't silently switch cases.
   - **Plan absent** (older path): fall back to reading `preconditions.data_setup` as before. Log a `live_update_findings` note that no plan existed.
8. **Component identity verification** + **Case fitness check** before any scenario. If the check fails and reconcile is needed, write `reconcile_start` and `reconcile_end` (Category C) around the fix.
9. For each scenario in `sidecar.scenarios` (array order):
   - Write `scenario_start` (Category B).
   - For each When action: write a `step` entry (Category B) before the action. For any `wait_for` that blocks > 3 s, also write a `wait` entry (Category B) after it returns.
   - If the Given state can't be constructed mid-scenario, write `reconcile_start` / `reconcile_end` (Category C) around the recovery work.
   - If server-side extraction polling is triggered: write `extraction_poll_start` (Category A) before the loop, `extraction_poll_wait` (Category A) each yield, `extraction_poll_end` (Category A) when done.
   - Before each `take_screenshot` call, write `screenshot_start` (Category D); after the file lands on disk, write `screenshot_end` (Category D).
   - Append every step to `trace.jsonl`.
   - Write `scenario_end` (Category B) after all assertions are evaluated.
   - Capture per-scenario screenshots under `04-run-<unit_id>-<ticket_id>/screenshots/`.
10. Write `result.json` to `artifacts/<run-id>/04-run-<unit_id>-<ticket_id>/result.json` per schema. Required: `run_id`, `unit_id`, `ticket_id`, `tickets`, `env`, `user_role`, `verdict`, `passed_primary`, `scenarios[]`. FAIL scenarios need a `fail_reason`. Live-update anomalies go in `live_update_findings[]`.
11. **Self-validate before returning**:
    ```bash
    scripts/validate-artifact.py --kind result --path artifacts/<run-id>/04-run-<unit_id>-<ticket_id>/result.json
    scripts/validate-artifact.py --kind trace  --path artifacts/<run-id>/04-run-<unit_id>-<ticket_id>/trace.jsonl
    ```
    Don't return success while either is invalid — the reporter refuses to read invalid artifacts.
12. Return: total scenarios, pass/fail breakdown, run-dir path, "result+trace validated".

**HARD RULE — before proceeding to Phase 5b (reporter):**
```
Read("prompts/linear-comment-template.md")
```
This must be the very next action after this runbook completes. Do not compose or post any Linear comment without first reading the template file fresh in context. Do not rely on memory. A comment written without reading the template is non-conforming and must be deleted and reposted.

## Anti-patterns

- ❌ Inventing assertions not in the spec ("page renders without errors") — only assert what Then clauses say.
- ❌ Hardcoding waits (`sleep 2s`). Use `wait_for` / `evaluate_script` polling.
- ❌ Screenshot or assert before confirming page load. Blank-background screenshots mean the trace is lying.
- ❌ Catching failures and silently retrying. Every failure must be in the trace.
- ❌ Skipping `trace.jsonl` or deferring it to the end. The first entry must be written before any browser action; each step appended immediately as it happens.
- ❌ Leaking secrets. If unsure, treat as sensitive.
- ❌ Treating the first popover/widget in the right region as the SUT. Pin the component identity from the diff and verify it lands; don't settle for a similar-looking sibling. (See Component identity verification.)
- ❌ Calling a scenario FAIL when the Given-state can't be constructed. Stop, find or create a fitting case, then run. A wrong-case FAIL is louder than a real bug and harder to retract.
- ❌ Reloading "to make the next step easier". Reload erases live-update bugs. (See Reloads are evidence-destroying.)
- ❌ Inventing test URLs for `download_url` / outbound-fetch scenarios when the PR test plan already specifies them. Read the PR body in `01-pr-diffs.json` before choosing test data — the dev's e2e verification section names the exact URLs and external_ids they used. Replicate those first; only fall back to S3 presigned URLs when the PR body has none. Using public external URLs (e.g. w3.org) on prod will always fail — the prod SSRF guard blocks all non-Supio external domains.
- ❌ Changing test data to work around a prod/dev behavior difference. When observed prod behavior differs from the PR's dev verification, record it as `[Warning]` in `live_update_findings[]` and report it — do not silently swap URLs to get the test to pass. The difference itself is a QA finding.
