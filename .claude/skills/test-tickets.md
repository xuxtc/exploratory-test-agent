---
name: test-tickets
description: Run the full exploratory-test-agent pipeline on one or more Linear tickets. Usage `/test-tickets SUP-123[,SUP-124,...] [--env=prod|stg]`. Orchestrates linear-fetcher → test-triage → test-strategist → test-executor → linear-reporter end-to-end without user prompts on the happy path. Only pauses when triage confidence is medium/low or a spec produces `open_questions`. The default env is prod (writes go to an isolated test tenant configured in env.prod.json).
---

# /test-tickets

You are orchestrating the exploratory-test-agent pipeline. The user has invoked you with a comma-separated list of Linear ticket IDs and optionally an `--env` flag.

## Arguments

- Ticket IDs (required): comma-separated, e.g. `SUP-7152,SUP-7497`
- `--env=prod|stg` (optional, default `prod`)

If no IDs are provided, ask the user for them before doing anything else. Do not invent ticket IDs.

The user may also trigger this with natural language. All of the following are equivalent to `/test-tickets <ids>`:
- 中文：`"测试 SUP-7152"`, `"帮我测 DOC-88"`, `"帮我测试 SUP-7152, ECO-7497"`, `"测一下 SUP-7152"`, `"跑一下 SUP-7152"`, `"验证 SUP-7152"`, `"这几个卡测一下 SUP-7152 ECO-7497"`, `"批量测试 SUP-7152,SUP-7497"`
- 英文：`"test ECO-1234"`, `"test these: ENG-1234"`, `"run SUP-7152"`, `"verify SUP-7152"`, `"check SUP-7152"`

If the user names an env in natural language ("on staging", "在 stg 环境", "stg 上测"), parse that into `--env=stg`.

## Pipeline

Execute these phases in order. **Announce each agent invocation before calling it** (per the project's transparency rule).

### Phase 0 — Setup

1. **Resolve AGENT_ROOT** — run this first, before anything else:
   ```bash
   REPO_ROOT=$(git rev-parse --show-toplevel)
   AGENT_ROOT="$REPO_ROOT/exploratory-test-agent"
   if [ ! -d "$AGENT_ROOT" ]; then
     echo "ERROR: Cannot locate exploratory-test-agent/ under repo root $REPO_ROOT. Abort."
     exit 1
   fi
   ```
   Store `$AGENT_ROOT` for all subsequent path construction. Every path in this skill that was previously `artifacts/<run-id>/...` is now `$AGENT_ROOT/artifacts/<run-id>/...` and every `scripts/...` call is now `$AGENT_ROOT/scripts/...` and every `config/...` read is now `$AGENT_ROOT/config/...`. This ensures artifacts always land in the correct subdirectory regardless of which directory Claude Code was opened from.

2. **Scan for a reusable analyze run** — before generating a new run-id, check whether `/analyze-tickets` was already run for these tickets:
   ```bash
   # Find the most recent artifacts directory that:
   #   (a) contains 00-analyze-output.json
   #   (b) whose name ends with _<first-ticket-id>
   ls -dt "$AGENT_ROOT/artifacts/"*_<first-ticket-id> 2>/dev/null | head -1
   ```
   Read that directory's `00-analyze-output.json` and confirm its `tickets` array contains **all** of the tickets being tested now (not just the first one). If it matches:
   - **Reuse that run-id** — do not generate a new one.
   - Tell the user: "Found existing analysis run `<run-id>` — reusing it. Scenarios from `/analyze-tickets` will be used directly."
   - Skip creating the artifacts directory (it already exists). Still touch the `.active` marker and write the timing entry.

   If no matching directory is found, or `00-analyze-output.json` is absent or covers different tickets:
   - Generate a new run-id: `<YYYY-MM-DD>_<HHMM>_<first-ticket-id>`. Use `date +%Y-%m-%d_%H%M`.
   - Create the run directory: `mkdir -p "$AGENT_ROOT/artifacts/<run-id>"`

3. Create the run directory if not already created in step 2:
   ```bash
   mkdir -p "$AGENT_ROOT/artifacts/<run-id>"
   ```
4. **Touch the active marker**:
   ```bash
   touch "$AGENT_ROOT/artifacts/<run-id>/.active"
   ```
   The intervention-logging hook (`.claude/hooks/log-intervention.sh`) only writes to `interventions.jsonl` while exactly one such marker exists; without this touch, no interventions will be captured for the run.
5. Read `$AGENT_ROOT/config/env.stg.json` or `$AGENT_ROOT/config/env.prod.json` (based on the chosen env). Verify the file exists and at least the `external` role has non-null credentials. If missing/malformed: stop with a clear error.
6. Tell the user: "Run id: `<run-id>`. Env: `<env>`. Artifacts will be at `$AGENT_ROOT/artifacts/<run-id>/`."
7. **Write the first timing entry** — append to `$AGENT_ROOT/artifacts/<run-id>/timing.log`:
   ```bash
   echo '{"ts":"'$(date -u +%Y-%m-%dT%H:%M:%SZ)'","phase":"run","event":"start","tickets":["SUP-XXXX"],"env":"<env>"}' >> "$AGENT_ROOT/artifacts/<run-id>/timing.log"
   ```
   Replace the placeholder ticket list and env with actual values. This file is JSONL — one JSON object per line. All subsequent timing entries append to this same file.

### Phase 1 — Fetch

**Skip if reusing an analyze run.** If Phase 0 found and reused an existing run-id (i.e. `00-analyze-output.json` was present), `01-fetch.json` and `01-pr-diffs.json` already exist — skip this phase entirely and proceed to Phase 2.

**Timing: write start entry before invoking the agent:**
```bash
echo '{"ts":"'$(date -u +%Y-%m-%dT%H:%M:%SZ)'","phase":"fetch","event":"start"}' >> "$AGENT_ROOT/artifacts/<run-id>/timing.log"
```

Invoke the `linear-fetcher` agent with the ticket list and run-id.

After it returns, **run pre-flight check** before proceeding:

```bash
python3 "$AGENT_ROOT/scripts/check-phase.py" --run-id <run-id> --phase fetch
```

If it exits non-zero, stop and surface the error to the user — the fetcher claimed done but didn't write what it owes. If any tickets errored (in `errors[]`), tell the user and ask whether to continue with the rest.

**Timing: write end entry after the pre-flight check passes:**
```bash
echo '{"ts":"'$(date -u +%Y-%m-%dT%H:%M:%SZ)'","phase":"fetch","event":"end","ticket_count":<N>}' >> "$AGENT_ROOT/artifacts/<run-id>/timing.log"
```
Replace `<N>` with the number of tickets that were successfully fetched.

### Phase 2 — Triage

**Timing: write start entry before invoking the agent:**
```bash
echo '{"ts":"'$(date -u +%Y-%m-%dT%H:%M:%SZ)'","phase":"triage","event":"start"}' >> "$AGENT_ROOT/artifacts/<run-id>/timing.log"
```

Invoke the `test-triage` agent with the run-id.

After it returns:

```bash
python3 "$AGENT_ROOT/scripts/check-phase.py" --run-id <run-id> --phase triage
```

Stop on non-zero exit.

After it returns, **read `02-triage.json` yourself** and present a summary table to the user:

```
| Ticket | Decision | Confidence | Role | Env | Reason |
|--------|----------|------------|------|-----|--------|
| SUP-7152 | Test (unit-1) | high | external | prod | Full new case create UX |
| SUP-7497 | Test (unit-1) | high | external | prod | Same milestone as 7152 |
| SUP-9999 | Skip | high | — | — | label: tech-debt |
```

**Env resolution after triage:** For each test unit, the effective `env` is determined as follows — **the user-specified `--env` flag always wins**; if no flag was given, use the `env` field that `test-triage` inferred from the ticket content. Carry the resolved env into every downstream phase (strategy, executor) for that unit. Different units in the same run may use different envs if triage inferred them differently.

Then:
- If `needs_user_review` is empty:
  - **Timing: write end entry:**
    ```bash
    echo '{"ts":"'$(date -u +%Y-%m-%dT%H:%M:%SZ)'","phase":"triage","event":"end","units":<N>,"skipped":<S>}' >> "$AGENT_ROOT/artifacts/<run-id>/timing.log"
    ```
    Replace `<N>` with test unit count and `<S>` with skipped ticket count. Then proceed to Phase 3.
- If `needs_user_review` has items:
  - **Timing: write user-review start entry:**
    ```bash
    echo '{"ts":"'$(date -u +%Y-%m-%dT%H:%M:%SZ)'","phase":"triage","event":"user_review_start","items":<N>}' >> "$AGENT_ROOT/artifacts/<run-id>/timing.log"
    ```
  - Use `AskUserQuestion` to ask:
    - For test units: "Proceed with testing this unit?" (Yes / Skip / Need more info)
    - For role uncertainty: "Run unit-X as <inferred-role>?" (Yes / Switch to other role)
    - For skipped tickets: "Confirm skip?" (Confirm / Test anyway)
  - After user input, update `02-triage.json` with the user's decisions (add a `user_overrides` section, don't rewrite the file).
  - **Timing: write end entry after user review is resolved:**
    ```bash
    echo '{"ts":"'$(date -u +%Y-%m-%dT%H:%M:%SZ)'","phase":"triage","event":"end","units":<N>,"skipped":<S>}' >> "$AGENT_ROOT/artifacts/<run-id>/timing.log"
    ```

### Phase 2.5 — Data Planning

**Timing: write start entry before invoking the agent:**
```bash
echo '{"ts":"'$(date -u +%Y-%m-%dT%H:%M:%SZ)'","phase":"data_plan","event":"start"}' >> "$AGENT_ROOT/artifacts/<run-id>/timing.log"
```

After triage finishes (and after any user-review pause is resolved), invoke the `test-data-planner` agent with the run-id. The planner reads `02-triage.json`, walks each unit's PR diffs, and decides per-unit whether to create a fresh case or reuse an existing one — and (for fresh cases) which fixture documents the case should contain. Output: `$AGENT_ROOT/artifacts/<run-id>/02b-data-plan.json`.

After it returns:

```bash
python3 "$AGENT_ROOT/scripts/check-phase.py" --run-id <run-id> --phase data-plan
```

Stop on non-zero exit — a malformed data plan would mislead the strategist and executor.

**No user gate at this phase.** The plan is recorded and visible in `02b-data-plan.json` and again in the final `05-summary.md`. If the planner had to auto-add an entry to `fixtures/manifest.json` via Drive search, the planner notes it in `02b-data-plan.json`'s `manifest_changes[]` — surface the count to the user when announcing Phase 3 starts ("Data plan written. N units in M case-groups (P fresh / Q reuse). K manifest entries auto-added — review before next run.").

**Timing: write end entry after pre-flight check passes:**
```bash
echo '{"ts":"'$(date -u +%Y-%m-%dT%H:%M:%SZ)'","phase":"data_plan","event":"end","manifest_changes":<K>}' >> "$AGENT_ROOT/artifacts/<run-id>/timing.log"
```
Replace `<K>` with the count from `02b-data-plan.json`'s `manifest_changes[]` array length (0 if empty).

If the plan has any `case_decision: blocked_no_fixture` entries, **still proceed to strategy** — the strategist will write the spec, the executor will FAIL the affected scenarios with the planner's `fixture_gap` reason, and the human gets a clear actionable signal in the Linear comment instead of a silently-skipped unit.

### Phase 3 — Strategy (parallel)

Spawn all surviving test units **concurrently** as separate `test-strategist` sub-agents. Each strategist reads only its own slice of the artifacts dir (`01-fetch.json`, `01-pr-diffs.json`, `02-triage.json`, `02b-data-plan.json`) and writes to its own sidecar path (`03-spec-<unit_id>-<ticket_id>.json`). There is no shared write state between units, so parallel invocation is safe.

For each test unit, before spawning:

1. Announce: "Generating spec for unit-X covering SUP-NNN, SUP-MMM (env=<env>, role=<role>)"
2. **Timing: write start entry:**
   ```bash
   echo '{"ts":"'$(date -u +%Y-%m-%dT%H:%M:%SZ)'","phase":"strategy","event":"start","unit_id":"<unit_id>","tickets":["SUP-NNN"]}' >> "$AGENT_ROOT/artifacts/<run-id>/timing.log"
   ```

Spawn all `test-strategist` agents in a single `Agent` call batch (parallel). After **all** have returned:

For each unit:
1. Run validation:
   ```bash
   python3 "$AGENT_ROOT/scripts/check-phase.py" --run-id <run-id> --phase spec --unit <unit_id>
   ```
   Stop on non-zero exit — a malformed spec must not reach the executor.
2. **Timing: write end entry:**
   ```bash
   echo '{"ts":"'$(date -u +%Y-%m-%dT%H:%M:%SZ)'","phase":"strategy","event":"end","unit_id":"<unit_id>","scenario_count":<N>}' >> "$AGENT_ROOT/artifacts/<run-id>/timing.log"
   ```
3. Briefly show the user each spec's title, scenario count, and any open questions.

### Phase 5 — Execute and Report (interleaved across units)

Phase 5 is the only phase that does **not** delegate execution to a sub-agent. Drive Chrome from your own (main-session) context, following `.claude/runbooks/test-executor.md` as a runbook. See that file's "Why this is not a sub-agent" section — `mcp__chrome-devtools__*` tools are deferred and do not propagate to spawned sub-agents on the current Claude Code build.

**Each unit gets its own isolated Chrome session via the chrome-proxy.** Pass `session_id: "<unit_id>"` on every `mcp__chrome-devtools__*` call for that unit (e.g. `session_id: "unit-1"`, `session_id: "unit-2"`). The proxy routes each call to a dedicated Chrome instance with its own `--userDataDir`, giving each unit fully isolated login state.

**Execution order within a unit remains strictly sequential** — scenario 1 → 2 → 3 in order. Only *inter-unit* work is interleaved.

**Interleaving strategy:** Process units in a cooperative loop. After completing any blocking wait within a unit (server-side extraction polling, `ScheduleWakeup` yields), switch to the next unit's next pending step rather than spinning idle. This keeps Chrome sessions productive during long waits. The canonical interleave point is the extraction-polling loop in `test-executor.md` — when a unit yields for 90-120s, advance the next unit until it also blocks or completes.

**If only one unit exists, run it straight through with no interleaving.** The interleave logic is additive overhead; skip it for single-unit runs.

**Flag conflict is not a concern.** Each unit has its own Chrome profile with independent `localStorage`. A unit needing `feature-X=ON` and a unit needing `feature-X=OFF` can run in the same session without conflict — their `localStorage.enabledFeatureFlags` keys are separate.

For each confirmed unit:

#### Phase 5a — Execute

1. Announce: "Executing unit-X via Chrome DevTools MCP (in-context, following test-executor runbook)"
2. **Timing: write start entry before any browser action:**
   ```bash
   echo '{"ts":"'$(date -u +%Y-%m-%dT%H:%M:%SZ)'","phase":"execute","event":"start","unit_id":"<unit_id>"}' >> "$AGENT_ROOT/artifacts/<run-id>/timing.log"
   ```
3. **Follow the executor runbook's first steps exactly** — read `.claude/runbooks/test-executor.md` and start from the top: first pkill stale Chrome MCP processes for this unit's session (as documented there), then run the ToolSearch call to load Chrome DevTools tools into context. Do the pkill + ToolSearch once per `/test-tickets` invocation; subsequent units in the same run reuse the loaded tools. **Note:** the pkill targets only `chrome-proxy-profile-<unit_id>` — never a global `pkill -f chrome-devtools-mcp`, which would kill Chrome instances belonging to other CC windows running concurrent tests. The proxy itself (`proxy_server.py`) must NOT be killed.
4. The executor is invoked **once per ticket**, not once per unit. For a unit with multiple tickets, loop through `unit.tickets[]` and execute the runbook sequentially for each ticket — each ticket gets its own `04-run-<unit_id>-<ticket_id>/` directory, its own `trace.jsonl`, and its own `result.json`. Browser auth may be reused across tickets in the same unit (check if already logged in before attempting login again). Treat every "you" in that document as referring to you, the orchestrator, in the current session. **The executor runbook will write its own fine-grained timing entries into the same `timing.log` during execution.** Pass `session_id: "<unit_id>"` to every `mcp__chrome-devtools__*` call — this is how the proxy knows which Chrome instance to route to.
5. After **all tickets in the unit** have been executed and artifacts written, run once per ticket:
   ```bash
   python3 "$AGENT_ROOT/scripts/check-phase.py" --run-id <run-id> --phase execute --unit <unit_id>
   ```
   This validates `result.json` and `trace.jsonl` against their schemas. The runbook tells you to self-validate before declaring done; this is defense in depth. If validation fails, fix the artifacts and re-run the check before continuing.
6. **Timing: write end entry after validation passes:**
   ```bash
   echo '{"ts":"'$(date -u +%Y-%m-%dT%H:%M:%SZ)'","phase":"execute","event":"end","unit_id":"<unit_id>","verdict":"<pass|fail|error>","scenarios_run":<N>}' >> "$AGENT_ROOT/artifacts/<run-id>/timing.log"
   ```
   Replace `<N>` with total scenario count and verdict with the unit-level verdict from `result.json`.

#### Phase 5b — Report (this unit only, immediately after execute)

**Timing: write start entry before invoking the reporter:**
```bash
echo '{"ts":"'$(date -u +%Y-%m-%dT%H:%M:%SZ)'","phase":"report","event":"start","unit_id":"<unit_id>"}' >> "$AGENT_ROOT/artifacts/<run-id>/timing.log"
```

5. **Do NOT invoke `linear-reporter` as a sub-agent.** Like the executor, the reporter is an **in-context runbook** — read `.claude/runbooks/linear-reporter.md` and follow its workflow yourself in the main session. A spawned sub-agent will not have the Linear MCP tools loaded and will skip the mandatory template-read step, producing non-conforming comments (this was the root cause of the SUP-7781 regression). Treat every "you" in that file as referring to you, the orchestrator.

   **HARD RULE — before writing a single word of any comment body:**
   ```
   Read("prompts/linear-comment-template.md")
   ```
   This step is mandatory and cannot be skipped or deferred. Do not rely on memory of the template from a previous session or earlier in this run. Every comment must be composed with the template file freshly loaded in context. If you have not read the file in this step, stop and read it now before continuing.

   When following the reporter runbook in per-unit mode, scope is: unit `<unit_id>` only — do not touch other units. Artifacts dir: `$AGENT_ROOT/artifacts/<run-id>/04-run-<unit_id>/`.

   **The orchestrator must verify screenshot upload happened.** After completing the reporter runbook steps, confirm that `scripts/attach-screenshot-to-comment.py` was called and printed `{"ok": true, "uploaded": N, ...}` with N > 0. If N is 0 and `result.json` has screenshots in `screenshot_picks_for_comment`, the upload step was skipped — call `scripts/attach-screenshot-to-comment.py` directly now for each screenshot pick before proceeding.

   If the reporter returns a non-success status (e.g. `result.json` validation failed late, Linear API error), surface it to the user but **do not abort the whole pipeline** — keep going to the next unit. Each unit's reporting is independent. The aggregate-mode reporter call at Phase 6 will surface any unit that didn't get its per-unit comment posted.

6. **Timing: write end entry after the reporter confirms screenshots uploaded:**
   ```bash
   echo '{"ts":"'$(date -u +%Y-%m-%dT%H:%M:%SZ)'","phase":"report","event":"end","unit_id":"<unit_id>","screenshots_uploaded":<N>}' >> "$AGENT_ROOT/artifacts/<run-id>/timing.log"
   ```
   Replace `<N>` with the screenshot count the reporter confirmed uploading.
7. Show the user a one-line status: "Unit-X: PASS/FAIL/error — Linear comment posted on TICKET-N." Plus the path to `04-run-<unit_id>/result.json` and `generated.spec.ts` if produced.

Then move on to the next unit and repeat 5a + 5b.

Run units **sequentially**. Do not parallelize — they share a Chrome session, and per-unit reporting is part of the per-unit boundary.

**Why per-unit reporting?** A 5-unit batch reporting only at end-of-run gives the human nothing for ~30 minutes, then a flood. Per-unit reporting puts the first ticket's result in front of the human in ~5 minutes, so they can interrupt the run on a real product bug instead of waiting for everything to finish.

**Why not a sub-agent for execute?** See `.claude/runbooks/test-executor.md`. Short version: deferred MCP tool schemas are not propagated to sub-agents at spawn time, so the sub-agent ends up unable to call any `mcp__chrome-devtools__*` tool. This was reproduced on extension v2.1.133 / CLI 2.1.25 across multiple sessions; the design now reflects the actual loader behavior rather than the intended one. If a future Claude Code release fixes deferred-tool propagation, this skill can be reverted to invoke a sub-agent — verify with a probe spawn first.

### Phase 6 — Aggregate

By this point every unit has already had its Linear comment posted in Phase 5b. Phase 6 only writes the aggregate summary and cleans up the run's session state.

1. **Do NOT invoke `linear-reporter` as a sub-agent.** Read `.claude/runbooks/linear-reporter.md` and follow its aggregate-mode workflow yourself in the main session. In aggregate mode there are no Linear writes — only rewrite `$AGENT_ROOT/artifacts/<run-id>/05-summary.md`. The template-read step (`Read("prompts/linear-comment-template.md")`) is **not required in aggregate mode** — no comment body is composed here.

2. **Remove the active marker**:
   ```bash
   rm "$AGENT_ROOT/artifacts/<run-id>/.active"
   ```
   From this point on, further user prompts will not be appended to this run's `interventions.jsonl` — they belong to whatever conversation comes next, not to this test run.

3. **Write the final timing entry** — this closes the run log:
   ```bash
   echo '{"ts":"'$(date -u +%Y-%m-%dT%H:%M:%SZ)'","phase":"run","event":"end","units_passed":<P>,"units_failed":<F>,"tickets_skipped":<S>}' >> "$AGENT_ROOT/artifacts/<run-id>/timing.log"
   ```
   Replace with actual counts from the aggregate summary.

Show the final summary:

```
Run <run-id> complete (env=<env>).
- N tickets fetched
- X skipped
- Y test units executed: P passed, F failed
- Z Linear comments posted
- Local report: $AGENT_ROOT/artifacts/<run-id>/05-summary.md

To archive a passing test to portal:
  /archive-to-portal <run-id>/<unit-id>
```

## Parallel execution

Phase 3 (strategy) runs all units concurrently. Phase 5 (execute) interleaves units at blocking-wait boundaries via the chrome-proxy's `session_id` isolation. See the Phase 3 and Phase 5 sections above for the full design.

### What is parallel vs sequential

| Scope | Mode | Reason |
|-------|------|--------|
| Phase 3 across units | **Parallel** | Filesystem-only sub-agents; each writes to its own sidecar path |
| Phase 5 across units | **Interleaved** | Each unit has its own Chrome session (`session_id`); switch units at extraction-poll yields |
| Scenarios within a unit | **Sequential** | Browser state has ordering dependency within a unit |
| Phase 5b (report) after a unit | **Immediate** | Post the Linear comment as soon as that unit's executor finishes, before moving to the next unit |

### Flag conflict policy (revised)

Flag conflicts **no longer block parallelism.** Each unit's Chrome instance has its own `localStorage`, so `enabledFeatureFlags` is independent per session. Two units requiring opposite values of the same flag can run concurrently without interference.

## Sub-agent retry policy

Every sub-agent invocation (`linear-fetcher`, `test-triage`, `test-data-planner`, `test-strategist`) must follow this retry policy:

1. Invoke the agent.
2. If the agent returns an `API Error` (socket closed, timeout, connection reset) **and the output artifact does not exist or is empty**: wait 10 seconds, then invoke the agent exactly once more with the same prompt.
3. If the retry also fails: stop, surface the error to the user, do not proceed to the next phase.
4. If the agent returns successfully but the pre-flight check (`check-phase.py`) fails: that is a correctness error, not a connectivity error — do **not** retry. Stop and surface the pre-flight output to the user.

The 10-second wait before retry is intentional — it gives the API gateway time to recover from a transient overload. Do not retry immediately.

Log the retry in timing.log:
```bash
echo '{"ts":"'$(date -u +%Y-%m-%dT%H:%M:%SZ)'","phase":"<phase>","event":"retry","reason":"API Error — socket closed"}' >> "$AGENT_ROOT/artifacts/<run-id>/timing.log"
```

This policy applies to all four sequential sub-agents. The parallel `test-strategist` invocations in Phase 3 each follow the same policy independently — a retry on one unit does not block other units.

## Hard rules

- **Pause for user confirmation between phases 2→3 only when triage produced `needs_user_review` items.** A clean high-confidence triage proceeds straight through. Phase 4 (confirm-before-execute) was removed: with `prod.external` in `env.prod.json` always pointing at the isolated test tenant, and with the run-id printed at Phase 0, the previous prod warning was friction without protection.
- **Never skip Phase 2 user review** for medium/low confidence items, even if the user said "do it all" earlier.
- **If any phase fails fatally, stop and tell the user.** Do not silently continue with partial state.
- **Phase 3 agents (test-strategist) may be called in parallel** — each unit writes to its own sidecar path and there is no shared write state. All other sub-agents (linear-fetcher, test-triage, test-data-planner) remain sequential — they write to shared files (`01-fetch.json`, `02-triage.json`, `02b-data-plan.json`).
- **Do not invoke `portal-archiver` from this skill.** Archival is a separate, manual step (`/archive-to-portal`) so the user can review `generated.spec.ts` first.

### Orchestrator note duty (powers `/retro`)

The intervention-logging hook captures every user prompt verbatim, but it can't see *what the orchestrator did in response*. Whenever you (the orchestrator) make a non-trivial course correction during a run — e.g. you re-scope a spec mid-flight, you stop dispatching to a sub-agent and drive the work yourself, you toggle a runtime flag because the spec didn't catch it, you switch surfaces (legacy AI assistant → case agent), or you change which env/account is used — append a single JSONL line to `$AGENT_ROOT/artifacts/<run-id>/interventions.jsonl` so that `/retro` can pair the user's prompt with what changed downstream.

Format:

```json
{"ts":"<ISO8601 UTC>","kind":"orchestrator_note","phase":"5b","trigger":"user said 'OAuth已经做过了'","decision":"narrowed spec to disconnect/reconnect cycle only; rewrote 03-spec-unit-1.md","why":"matched spec to actual test data state to avoid blocked scenarios"}
```

Rules:
- Only log notes that would matter to a future retro — i.e. the kind of thing that, in hindsight, suggests an agent or skill should have done it without prompting. Routine "I picked option A from the AskUserQuestion you presented" is NOT a note; the hook already captured the prompt and the option chosen is in your reply.
- Keep `decision` and `why` ≤ 25 words each. `/retro` reads many of these in sequence; long notes hide the signal.
- Never append while no `.active` marker exists. If you genuinely need to log something post-Phase-6, surface it to the user instead.

## Anti-patterns

- ❌ Inventing ticket IDs because the user didn't provide any
- ❌ Reading `01-fetch.json` and re-doing triage yourself instead of invoking `test-triage`
- ❌ Posting to Linear before all units have been executed (or skipped intentionally)
- ❌ Adding back a "are you sure?" confirmation between Phase 3 and Phase 5. The user removed it on purpose. If you think a particular spec is too risky to auto-execute, that risk belongs in the spec's `[skip-on-this-pass]` scenarios or in `Open questions`, not in a global confirmation prompt.
