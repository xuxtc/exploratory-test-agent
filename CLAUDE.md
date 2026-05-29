# CLAUDE.md

This file is the operating manual for the **exploratory-test-agent** project. Claude Code reads it on every session to understand how to behave in this repository.

## Project Purpose

`exploratory-test-agent` is a **test agent** that performs LLM-driven exploratory testing — instead of running pre-written scripts, it looks at the page, decides the next action, and adapts to UI variation. It takes Linear ticket IDs, decides which need E2E testing, plans the test strategy, **executes the tests in a real browser via the Chrome DevTools MCP**, and reports results back to Linear.

Inputs: Linear ticket IDs.
Outputs:
1. A triage report (which tickets need testing, why, what user role)
2. A test strategy and Requirement Spec for each test unit
3. **An executed test run** — screenshots, trace, pass/fail per scenario
4. A comment posted on each ticket summarizing results

`trace.jsonl` and `03-spec.md` live in `artifacts/` (gitignored) until the user explicitly runs `/archive-to-portal`, at which point they are copied to `$PLAYWRIGHT_REPO_PATH/.claude/incoming/` for the portal's `add-test` pipeline.

## Companion Repository

`<your-playwright-repo>` (path: `$PLAYWRIGHT_REPO_PATH`) is the canonical Playwright regression suite. It is **not** in the execution path of `/test-tickets` — it is the **archive destination** for tests that pass review.

## Pipeline Overview

```
User: /test-tickets SUP-7152,SUP-7497 [--env=stg|prod|prod-ca]
         │
         ▼
┌────────────────────┐
│ linear-fetcher     │  reads Linear via MCP
└────────────────────┘
         │  artifacts/<run-id>/01-fetch.json
         ▼
┌────────────────────┐  rule-based + LLM triage
│ test-triage        │  outputs: skip vs test, clusters,
└────────────────────┘  inferred user_role (default: external)
         │  artifacts/<run-id>/02-triage.json
         ▼
   USER CONFIRMATION (medium/low confidence + role inference)
         │
         ▼
┌────────────────────┐  decides per unit: create_fresh vs reuse_existing case;
│ test-data-planner  │  picks fixtures from manifest by covers_event_types;
└────────────────────┘  auto-adds manifest entries via Drive search when needed
         │  artifacts/<run-id>/02b-data-plan.json
         ▼
┌────────────────────┐  per test unit; binds spec to data plan's case decision
│ test-strategist    │  produces Requirement Spec
└────────────────────┘  (env, role, scenarios, preconditions)
         │  artifacts/<run-id>/03-spec-<unit>.md
         ▼
┌────────────────────┐  drives Chrome via Chrome DevTools MCP
│ test-executor      │  records every step (trace.jsonl)
└────────────────────┘  takes screenshots, evaluates assertions
         │  artifacts/<run-id>/04-run-<unit>/
         │    ├── trace.jsonl
         │    ├── screenshots/
         │    └── result.json
         ▼
   USER REVIEW (results + trace)
         │
         ▼
┌────────────────────┐  posts comment on each ticket
│ linear-reporter    │  with results + screenshots + run-id
└────────────────────┘

   Optional, manual:
   /archive-to-portal <run-id>/<unit-id>
         │
         ▼
┌────────────────────┐  copies 03-spec.md + trace.jsonl into
│ portal-archiver    │  portal's .claude/incoming/ — never auto-pushes
└────────────────────┘

   Optional, manual:
   /sync-test-cases <run-id>[/<unit-id>]
         │
         ▼
  test-case-generator-agent/sync.py --from-run
  reads result.json + spec sidecar → builds structured
  test cases from executed scenarios → dedup + preview
  diff → writes to Google Sheets on confirmation
```

## Hard Rules

### PR diff is mandatory before any test scenario output

**Before listing or planning any test scenarios for a ticket, the PR diff and PR description must both have been fetched and read.** Specifically: `01-pr-diffs.json` must exist and contain at least one non-skipped PR entry for that ticket. If no PR diff has been fetched yet, fetch it first via `linear-fetcher`. When a PR description (body) is present, it must be read alongside the diff — the two together form the complete picture of intent vs. implementation. Never output test scenarios based solely on ticket title, description, or existing comments — PR diff and PR description are required inputs for triage and scenario planning.

This rule applies even when the pipeline is run partially or informally (e.g. user asks to "list scenarios" without going through the full `/test-tickets` flow). There are no exceptions.

### Production safety for internal and teams-tagged accounts (highest priority — overrides all other rules)

**Whitelisted test companies (prod):**
- `internal` account → the designated internal test company (57blocks / Supio tenant)
- `external[tags=teams]` account (`teamQAadmin@test.com`) → **"QA Test Team Company"**

The `internal` account has cross-company privileges and can read/write data belonging to companies other than the designated test company. The `external[tags=teams]` account is scoped to "QA Test Team Company" but still must not write outside that company. The blast radius of a wrong write is real customer data. These rules apply whenever `env=prod` AND `user_role=internal OR team`, and they override any spec, scenario, planner instruction, or user prompt — if those conflict, surface the conflict and refuse to execute, do NOT ask the user to override.

- **Company scope is locked to the whitelisted test company for the active account.** Do not switch tenants/companies via any UI affordance (company switcher, "switch to" link, admin-impersonate flow), URL change (`?company_id=...`, `/companies/<id>/...`), or API call. The session must end the run on the same company it started on.
- **Reads outside the whitelisted company are still discouraged but not forbidden.** If the agent inadvertently lands on a non-whitelisted surface (deep link, redirect), navigate back immediately and log an `unintended_company_navigation` finding. Do NOT click around.
- **Writes outside the whitelisted company are absolutely forbidden.** No update / delete / archive / file upload / field edit / case-state change / comment / status change against any case in any company other than the whitelisted company. There is no override.
- **Inside the whitelisted company, writes are restricted to `deqtest_`-prefixed cases.** Even within the correct company, the agent must never perform a write operation against a case whose visible display name does not start with `deqtest_`. Other test cases in the tenant may belong to teammates and breaking them costs human time. Read-only navigation of non-`deqtest_` cases is allowed.
- **Pre-write check is mandatory.** Before any state-mutating action under prod-internal or prod-team, the executor must verify (a) the page is on a URL that belongs to the whitelisted company for the active account, and (b) the target case's display name starts with `deqtest_`. If either check fails, abort the scenario, mark it FAIL with reason `prod safety check: <which gate failed>`, screenshot the page as evidence, and stop the unit. The orchestrator does not retry, does not prompt the user, does not silently skip — it stops.
- **/create-case is exempt from the deqtest_ check at the moment of clicking Create**, because the case doesn't exist yet — but the case_name being submitted must already start with `deqtest_`, and that's checked before clicking Create. Post-create, the new case naturally satisfies the rule.

### Orchestrator must not inline sub-agent work

**Each pipeline stage must be executed by its designated sub-agent — the orchestrator must never inline a stage's work itself.**

The agents `linear-fetcher`, `test-triage`, `test-data-planner`, and `test-strategist` are sub-agents with their own `.claude/agents/<name>.md` definitions. The orchestrator's role is to invoke them in order and pass artifacts between them — not to perform their reasoning directly.

Specifically:
- After `linear-fetcher` returns, the orchestrator must spawn `test-triage` as a sub-agent. It must NOT read `01-fetch.json` / `01-pr-diffs.json` and apply triage judgment inline.
- After `test-triage` returns, the orchestrator must spawn `test-data-planner` as a sub-agent. It must NOT make data-plan decisions inline.
- After `test-data-planner` returns, the orchestrator must spawn `test-strategist` as a sub-agent. It must NOT write specs inline.

Violation of this rule causes sub-agent-specific hard rules (e.g. Layer 1 deterministic skips in `test-triage`, data confidence gates in `test-data-planner`) to be silently skipped, because the orchestrator has not read those agent definition files.

`test-executor` and `linear-reporter` are **in-context runbooks** (not sub-agents) — the orchestrator follows their `.md` files directly in the main session. This is intentional and documented in the Agent Roster. **Before executing either runbook, the orchestrator must read the corresponding `.md` file first** (`Read(".claude/runbooks/test-executor.md")` / `Read(".claude/runbooks/linear-reporter.md")`). Never execute a runbook from memory — always read the file fresh.

### Confidence gating

- `test-triage` classifies each ticket as `high` / `medium` / `low` confidence.
- `medium` and `low` confidence tickets must be presented to the user for confirmation before proceeding.
- The inferred `user_role` (internal / external) must also be confirmed when not derivable with high confidence from the ticket. Default is `external`.
- Never silently skip a ticket — every skipped ticket must have a written reason.

### Missing test data — never skip without asking

When a scenario requires data that doesn't currently exist in the test environment, the executor must **not silently skip the scenario**. Instead:

1. Pause and present the blocker to the user: what data condition is needed, what was tried, why it can't be constructed.
2. Ask the user to choose: (a) skip permanently, (b) defer to a future run, or (c) suggest how to construct the data.

**Temporary data mutations are allowed** (e.g. temporarily removing a user from a team to simulate "no group membership"). When mutating:
- Screenshot the original state before mutating.
- Restore the original state immediately after the scenario, before moving to the next scenario.
- Log mutation and restoration in `trace.jsonl`.

See `context/test-data/temp-mutation.md` for the full procedure and allowed mutation types.

### Data confidence gating (enforced between Phase 3 and Phase 4)

After `test-strategist` completes all specs for a run and **before** `test-executor` is invoked for any unit, the orchestrator MUST:

1. Scan every `03-spec-*.json` for scenarios where `data_confidence` is `"low"` or `"medium"`.
2. If any `"low"` scenarios exist: **stop and present them to the user.** Format:

   ```
   ⚠️ The following scenarios need your input before execution can proceed:

   [LOW] Scenario N "<title>" — <data_blocker>
   [LOW] Scenario M "<title>" — <data_blocker>

   For each: should we (a) defer to a future run, (b) prepare the data now (describe how), or (c) skip permanently?
   ```

   Do not start any executor run until the user has responded to every `low` item.

3. If only `"medium"` scenarios exist (no `"low"`): surface them as informational warnings and proceed — medium scenarios have a known same-session workaround documented in `data_blocker`, so execution can start without blocking.
4. After user confirms each `"low"` scenario's disposition, update that scenario's `kind` to `"skip"` and `skip_reason` to the user's answer if they chose defer or skip, OR update `data_confidence` to `"medium"` and document the agreed preparation method in `data_blocker` if they chose to prepare the data now.

**This gate is not optional.** Scenarios whose data cannot be constructed in the current session must not be handed to the executor — executor time spent discovering a missing prerequisite is wasted time. The gate converts that discovery cost from runtime to pre-flight.

### Test environment

- The default execution environment is **prod**. STG can be selected with `--env=stg`. Canadian prod can be selected with `--env=prod-ca`.
- Real credentials live in `config/env.stg.json` and `config/env.prod.json` (committed to the private repo).
- `internal` and `external` user accounts are defined per environment in `config/env.<env>.json`. The spec/triage decides which role each unit needs (default `external`). When the ticket requires teams-related features, triage outputs `user_role: "team"` — the executor resolves this to the `external` account with `tags: ["teams"]` (`teamQAadmin@test.com`); prod writes must use `deqtest`-prefixed cases.
- **Shared account context** lives in `context/test-accounts/`. Read it before choosing an account for a prod run — it documents which company each account belongs to, what connectors are available, and when to defer scenarios. Key entry: `context/test-accounts/prod-external.md` (the `external` prod account, no connectors).
- The agent reads credentials from the local config file at runtime and **never echoes passwords into chat, logs, artifacts, or commit messages**.
- Production tests run against an **isolated test tenant** — writes do not affect real customer data.

### Feature flag conventions (Portal business context)

Business rules for feature flags live in `context/feature-flags/`. The index is at `context/feature-flags/index.md` — one row per known flag, with a pointer to the detail file. Agents consult this directory when analyzing which flags a test scenario requires (see `test-strategist.md` step 4b).

### Portal route map (ambiguous surface names)

Portal URL → UI surface mappings live in `context/portal-routes/`. Consult `context/portal-routes/index.md` **before writing a spec's Given/preconditions** whenever a ticket mentions a surface name that could map to multiple routes (e.g. "inbox", "mailroom", "overview"). Getting the route wrong wastes the entire executor run on the wrong page.

**Adding new rules:** See `context/README.md` for the full convention — where to put the file, how to update the index, and commit message format. Do not add business rules directly into CLAUDE.md. When asked to add a business rule, read `context/README.md` first and follow the conventions there.

### Artifacts directory

- Every run creates a unique directory: `artifacts/<YYYY-MM-DD_HHMM>_<first-ticket-id>/`.
- All intermediate JSON, specs, traces, screenshots, generated code go here.
- `artifacts/` is gitignored — it is local working state, not source.

### Cross-repo boundary

- This repo **never** imports from `portal-ui-automation`.
- This repo **does** write to `$PLAYWRIGHT_REPO_PATH` only during `/archive-to-portal`, never during `/test-tickets`.
- `portal-archiver` creates a branch in the portal repo but never pushes; the user runs `git push` manually after review.

### Linear write operations

- `linear-reporter` is the only agent that writes to Linear, and only via `save_comment`. No state changes, no labels, no relationships, no milestones — only the human ticket owner sets those.
- All comments include the run-id and link to the local report path.
- **Never create relationships between tickets** (`relatedTo`, `blocks`, `blockedBy`, `parentId`, `duplicateOf`, `links`, etc.). Co-occurrence in a `/test-tickets` run is a workflow detail, not a semantic relationship. This rule applies to every agent — if a future agent gets `mcp__linear__save_issue` in its tools, it must explicitly justify why and still must not touch relationship fields.
- **Linear auto-creates "related issue" backlinks from ticket IDs mentioned in comment bodies.** A comment on `LIN-A` containing the literal string `LIN-B` triggers a server-side mention parser that logs an "added related issue" entry on `LIN-B`. No agent permission can prevent this. Mitigation: a comment on `LIN-A` must not contain `LIN-B` unless the comment is genuinely about `LIN-B`'s subject matter. Cross-ticket workflow context belongs in local `05-summary.md`, never in the Linear comment body.

## Agent Roster

| Agent | Kind | Purpose |
|-------|------|---------|
| `linear-fetcher` | sub-agent | Pull ticket data via Linear MCP |
| `test-triage` | sub-agent | Decide test/skip, cluster tickets into units, infer user role |
| `test-data-planner` | sub-agent | Decide create-fresh vs reuse-existing case per unit; pick fixtures by event-type coverage |
| `test-strategist` | sub-agent | Produce Requirement Spec per test unit |
| `test-executor` | **in-context runbook** | Drive Chrome via Chrome DevTools MCP, record trace, evaluate assertions. NOT a sub-agent — orchestrator follows `.claude/runbooks/test-executor.md` in the main session. See that file for why and don't try to revert. |
| `linear-reporter` | **in-context runbook** | Post results back to Linear (per-unit + aggregate modes). NOT a sub-agent — orchestrator follows `.claude/runbooks/linear-reporter.md` in the main session. Same reason as executor: mandatory steps (template read, screenshot upload) must not be delegated to a sub-agent that can silently skip them. |

Each agent's tools, inputs, and detailed rules live in its own `.claude/agents/<name>.md` — do not duplicate them here.

## Skills

| Skill | Trigger | Purpose |
|-------|---------|---------|
| `/test-tickets` | `/test-tickets SUP-XXX[,SUP-YYY,...] [--env=prod\|stg\|prod-ca]` | Main pipeline (fetch → triage → spec → execute → report) |
| `/archive-to-portal` | `/archive-to-portal <run-id>/<unit-id>` | Manual: copy `03-spec.md` + `trace.jsonl` into portal's `.claude/incoming/` |
| `/sync-test-cases` | `/sync-test-cases <run-id>[/<unit-id>]` | Manual: sync executed scenarios from a passing run into Google Sheets test case library; uses `--from-run` mode of `test-case-generator-agent/sync.py` |
| `/create-case` | `/create-case [case-name] [--kind <type>] [--add <fixture>]` | Create a fresh AI-artifact-first test case in the Portal with fixture upload; called by executor during data-setup phase |
| `/switch-account` | `/switch-account --role internal\|external [--tag <tag>] [--env prod\|stg\|prod-ca]` | Switch the logged-in Portal account mid-run via the avatar-menu logout; preserves localStorage feature-flag overrides |
| `/toggle-feature-flag` | `/toggle-feature-flag --flag <name> on\|off` | Enable or disable a Portal feature flag via localStorage override + reload; checks backend entitlement first and refuses if the flag is not granted server-side |
| `/retro` | `/retro <run-id>` | Post-run retrospective: reads `interventions.jsonl`, identifies agent behavior gaps, and writes `06-retro.md` with concrete fix proposals per agent/skill/template file |
| `/analyze-tickets` | `/analyze-tickets SUP-XXX[,SUP-YYY,...] or Linear URL` | Analyze tickets and produce bilingual (CN+EN) E2E test case tables — no execution, no external writes |

### Trigger styles

`/test-tickets` is the canonical entry. The user may also trigger the same flow with natural language — when the user says something like "测试 SUP-7152, SUP-7497" or "test these tickets: ENG-1234", treat it as `/test-tickets <comma-separated-ids>` and invoke the skill.

`/sync-test-cases` can also be triggered with natural language — "固化用例", "形成测试用例", "sync test cases", "把用例写进 sheet", "固化这次测试". When a run-id is evident from context (e.g. it was mentioned in the same conversation), pass it automatically. If ambiguous, ask before proceeding.

`/analyze-tickets` can also be triggered with natural language — "分析 SUP-7152", "分析一下 SUP-7152, SUP-7497", "帮我分析一下这几个票 SUP-7152", "分析 https://linear.app/supio/issue/SUP-7849/...", "analyze tickets SUP-7152". Accepts both ticket IDs and Linear URLs — extract the ID from the URL automatically. Do NOT invoke for "测试 XXX" / "帮我测 XXX" / "跑一下 XXX" / "验证 XXX" — those go to `/test-tickets`.

`/archive-to-portal` can also be triggered with natural language — "推送 XXX 到 playwright", "archive XXX to portal", "把 XXX 推给 playwright", "归档到 playwright", "ship XXX to playwright", "automation XXX", "自动化 XXX". When the user names a ticket ID (e.g. "自动化 DOC-3144", "automation SUP-7152"), look up the most recent run in `artifacts/` whose run-id contains that ticket ID, find its unit-id, and pass `<run-id>/<unit-id>` automatically. If multiple units exist or no matching run is found, ask the user to specify.

## Environment

Required configuration (all in gitignored local files):

| File | Purpose |
|---|---|
| `.claude/settings.local.json` | `PLAYWRIGHT_REPO_PATH` env var, additional dirs |
| `config/env.stg.json` / `config/env.prod.json` / `config/env.ca.json` | Test URLs + credentials per env (stg, prod, prod-ca) per role (internal, external) |

Each has a corresponding `.example` checked in. **Both files are required**; the agent must error early with a clear message if either is missing or malformed.

The Linear MCP server uses a Personal API Key (`LINEAR_API_KEY`) stored in `config/dispatch-env.json`. Ticket IDs already carry their team prefix (e.g. `SUP-7152`), so a single workspace can mix tickets from any team.

## What This Repo is NOT

- Not a permanent home for Playwright code — generated specs live in `artifacts/` and are archived to portal only on demand.
- Not a long-running service — every invocation is a one-shot run triggered manually.
- Not a debugging environment for portal regressions — debug those in `portal-ui-automation`.

## Common Operations

```bash
./scripts/verify-mcp.sh                                # smoke-check Linear MCP
ls artifacts/<run-id>/                                 # inspect a run's artifacts
> /archive-to-portal <run-id>/<unit-id>                # ship passing test to portal (manual)
> /sync-test-cases <run-id>                            # sync executed scenarios → Google Sheets (manual)
> /sync-test-cases <run-id>/unit-1                     # sync a single unit only
> /retro <run-id>                                      # post-run retro → artifacts/<run-id>/06-retro.md

# Fixture management
python3 scripts/get-fixture.py --list                  # list all fixtures in manifest
python3 scripts/get-fixture.py --name "MRnMB.pdf"     # download fixture to cache

# Artifact validation (run after executor writes result.json / trace.jsonl)
python3 scripts/validate-artifact.py --kind result --path artifacts/<run-id>/04-run-unit-1/result.json
python3 scripts/validate-artifact.py --kind trace  --path artifacts/<run-id>/04-run-unit-1/trace.jsonl

# First-time setup
./scripts/install-shell-hooks.sh                       # auto-load .claude/settings.local.json env on cd
python3 scripts/google-drive.py auth                   # authenticate Google Drive for fixture downloads
```

## Why This Architecture

- **Agent-first execution**: an LLM that looks at the page and decides the next action is more robust to UI variation than pre-written selectors.
- **Playwright as the artifact, not the runtime**: trace → `.spec.ts` happens only after the test passes, so what gets archived is a known-working recording.
- **Reviewed archival**: portal stays clean because nothing lands there until a human approves.
- **Confidence gating**: triage is honest about uncertainty (Linear data is incomplete) rather than guessing.
