# exploratory-test-agent

[![Status](https://img.shields.io/badge/status-POC-orange)](#)
[![License](https://img.shields.io/badge/license-TBD-lightgrey)](#license)
[![Built with Claude Code](https://img.shields.io/badge/built%20with-Claude%20Code-7C3AED)](https://claude.com/claude-code)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen)](#contributing)

[English](./README.md) · [简体中文](./README.zh-CN.md)

> **Turn tickets into executed E2E tests, then archive the recording — not the guess.**

An LLM-driven exploratory testing agent that takes ticket IDs, drives a real browser end-to-end against your app, and only after a test actually passes does it generate a Playwright `.spec.ts`. The generated spec is therefore a **recording of a known-working path**, not pre-written selectors against assumptions.

Built on [Claude Code](https://claude.com/claude-code) using its agent + skill primitives. Writes a comment back to each ticket with screenshots and a result summary.

> **Status: POC.** Run small batches, review every stage, expect the agent to ask before doing anything irreversible.

---

## Why this exists

Traditional Playwright suites are written **ahead of time** against assumptions about the DOM. They break the moment the UI shifts and need constant maintenance. They also don't help you triage a ticket — they tell you whether a known flow still works, not whether _this specific change_ in PR #1234 actually does what the ticket said it would.

This agent flips both:

1. **The agent looks at the page** (DOM snapshot + screenshot) and decides the next click on the fly. UI variation is far easier to absorb at run-time than to pre-encode.
2. **The agent reads the linked PR's diff** (via the GitHub MCP) before writing scenarios. It tests what the PR _actually shipped_, not what the ticket prose promised.
3. **The trace is the artifact.** A run produces a `trace.jsonl` recording every step taken. The portal's `add-test` pipeline reads the trace (alongside the Requirement Spec) to generate Page-Object-style Playwright code — no intermediate `.spec.ts` translation needed.

---

## How it works

### Pipeline

```
ticket IDs ──▶ fetch ──▶ triage ──▶ [confirm] ──▶ data-plan ──▶ spec ──▶ execute ──▶ report ──▶ ticket comment
                                                                            │              ▲
                                                                     (drives Chrome  (per-unit:
                                                                      via MCP,        each ticket's
                                                                      records every    comment posts
                                                                      step)            the moment its
                                                                            │          unit finishes)
                                                                            ▼
                                                    ┌───────────────────────────────────────────────┐
                                                    │ optional, manual                              │ optional, manual
                                                    ▼                                              ▼
                                          /sync-test-cases                              /archive-to-portal
                                     executed scenarios ──▶                        03-spec.md + trace.jsonl ──▶
                                       Google Sheets                              portal/.claude/incoming/
                                      test case library                                    │
                                                                                           ▼
                                                                              portal add-test pipeline
                                                                           (Page Object + fixture style)
```

### The agents

| Agent | Job | Reads | Writes |
|---|---|---|---|
| `linear-fetcher` | Pull ticket bodies, comments, attachments | Tracker MCP | `01-fetch.json` |
| `test-triage` | Decide test/skip per ticket; cluster into units; infer user role | `01-fetch.json` | `02-triage.json` |
| `test-data-planner` | Decide create-fresh vs reuse-existing case per unit; pick fixtures by event-type coverage; auto-add manifest entries via Drive search | `02-triage.json`, GitHub MCP, `fixtures/manifest.json` | `02b-data-plan.json` |
| `test-strategist` | Read each linked PR's diff; run a three-pass gate scan (direct flag refs → MobX/store getter wrappers → lazy imports) to classify each gate as a feature flag or a data gate; write a Requirement Spec grounded in shipped code; bind data_setup to the data plan | `02b-data-plan.json`, GitHub MCP | `03-spec-<unit>.md` + `.json` sidecar |
| `test-executor` | Drive Chrome step-by-step; record every action; evaluate Then-clauses. **In-context runbook** (`.claude/runbooks/test-executor.md`), not a sub-agent — driven by the orchestrator's main session because Chrome DevTools MCP tools are deferred and don't propagate to spawned sub-agents. | `03-spec-<unit>.json`, `02b-data-plan.json`, Chrome DevTools MCP | `trace.jsonl`, `screenshots/`, `result.json`, `generated.spec.ts` |
| `linear-reporter` | Post a comment to each ticket with the result + screenshots. Reads `prompts/linear-comment-template.md` before composing every comment to enforce a consistent format. Two modes: per-unit (one comment per ticket as each unit finishes) and aggregate (writes `05-summary.md` at end of run). **In-context runbook** (`.claude/runbooks/linear-reporter.md`), not a sub-agent. | `result.json`, `prompts/linear-comment-template.md` | tracker comment + `05-summary.md` |

### Confidence gating

Tracker data is incomplete. Every triage decision carries a `high` / `medium` / `low` confidence and an inferred user role. Medium and low decisions, plus any ambiguous role inference, are surfaced for explicit user confirmation. **No ticket is silently skipped** — every skip carries a written reason in `02-triage.json`.

### Schema-validated artifacts

Every run lands a directory under `artifacts/<run-id>/` (gitignored). The pipeline phases hand off through files, not in-memory message passing — each artifact is JSON Schema-validated by `scripts/check-phase.py` between phases, so a malformed hand-off stops the pipeline early instead of poisoning downstream agents:

```
artifacts/<run-id>/
├── 01-fetch.json               # raw ticket data
├── 02-triage.json              # decisions + confidence per ticket
├── 02b-data-plan.json          # per-unit case_decision (create_fresh / reuse_existing) + fixtures
├── 03-spec-<unit>.md           # Requirement Spec (human-readable)
├── 03-spec-<unit>.json         # same spec, machine-readable (the contract executor reads)
├── 04-run-<unit>/
│   ├── trace.jsonl             # one JSON object per step (schema-validated)
│   ├── screenshots/            # PNGs at every checkpoint + on every failure
│   └── result.json             # pass/fail per scenario (schema-validated)
├── case-group-<N>/
│   └── case_id.txt             # the case the executor created/reused for this group; sibling units in the same group reuse it
└── 05-summary.md               # final aggregated run report
```

Schemas live in [`schemas/`](./schemas/); the validator is `scripts/validate-artifact.py`.

### Reviewed archival

`<your-playwright-repo>` (the canonical regression suite) stays clean: nothing lands there until you explicitly run `/archive-to-portal`. That copies `03-spec.md` + `trace.jsonl` into `.claude/incoming/`; the portal's `add-test` pipeline then generates the actual Playwright code. This repo never pushes to the portal repo.

### Parallel Chrome sessions

The `chrome-proxy/proxy_server.py` MCP proxy sits in front of `chrome-devtools-mcp` and multiplexes it across multiple isolated Chrome instances. Every tool call accepts an optional `session_id` parameter; calls with different `session_id` values are routed to separate Chrome processes, each with its own `--userDataDir` and therefore fully isolated login state, cookies, and localStorage.

This means you can run concurrent test units against different accounts or environments without sessions interfering with each other:

```
session-prod-internal  →  Chrome A (prod, internal account)
session-prod-external  →  Chrome B (prod, external account)
session-prod-ca        →  Chrome C (ca-portal, CA account)
```

Omit `session_id` (or pass `"default"`) and the proxy behaves like a single-session `chrome-devtools-mcp` — fully backward compatible.

The proxy is configured in `.mcp.json` and starts automatically with Claude Code. Idle sessions (no tool calls for 5 minutes) are cleaned up automatically.

### Credentials never leave the box

Test creds are read once at the start of a run and kept in agent-local memory. Passwords are masked before screenshots, never appear in `trace.jsonl` / `result.json` / `generated.spec.ts` / chat. The generated spec references env-var placeholders, never inline values.

---

## Quickstart

### Prerequisites

- [Claude Code](https://claude.com/claude-code)
- Node 20+ (for `npx mcp-remote`)
- Python 3.11+ (helper scripts; stdlib only)
- Chrome
- A ticket tracker workspace + tickets to test (Linear MCP is the reference integration)
- GitHub PAT for the repo whose PRs your tickets reference
- Google account with access to your team's fixture Drive folder (OAuth client JSON saved to `google-oauth-client.json` at repo root)
- _(optional)_ a Playwright repo to archive passing tests into — your `<your-playwright-repo>`

Full step-by-step setup (4 MCP servers + OAuth dances) is in **[docs/SETUP.md](./docs/SETUP.md)**. Plan ~20 minutes the first time.

### Run a test

Inside a Claude Code session in this repo:

```
> /test-tickets LIN-123,LIN-456
```

Defaults to **prod**. Use `--env=stg` to switch. Natural language works too — `测试 LIN-123, LIN-456` is treated the same.

The agent pauses for **user confirmation** only when triage is uncertain — medium/low confidence on any ticket, or an inferred user role that can't be derived from the ticket. A clean high-confidence triage runs straight through to reporting. Each ticket's comment posts the moment its unit finishes executing, so the human sees per-ticket results in real time instead of waiting for the whole batch.

### Inspect a run

Open `artifacts/<run-id>/` — every artifact is plain JSON or markdown. The ticket comment links back to it.

### Sync scenarios to the test case library

After a passing run, write the executed scenarios into your Google Sheets test case library:

```
> /sync-test-cases 2026-05-07_1430_LIN-123
```

Reads `result.json` + `03-spec` sidecar, builds structured test cases (Given/When/Then), shows a diff preview (NEW / UPDATE / SKIP), and writes on confirmation. Only runs with `passed_primary: true` are accepted.

### Archive a passing test to your Playwright repo

After a run passes, you can promote the executed spec into the canonical Playwright regression suite. The two-step flow:

**Step 1 — hand the spec over (in this repo)**

Use the ticket ID — the agent resolves the run automatically:

```
> 把 LIN-123 推给 playwright
```

Or with an explicit run-id/unit:

```
> /archive-to-portal 2026-05-07_1430_LIN-123/unit-1
```

Natural language equivalents (all treated identically):
- `推送 LIN-123 到 playwright`
- `把 LIN-123 归档到 playwright`
- `archive LIN-123 to portal`
- `ship LIN-123 to playwright`
- `automation LIN-123`
- `自动化 LIN-123`

What happens: `03-spec-unit-1.md` and `trace.jsonl` are copied into `$PLAYWRIGHT_REPO_PATH/.claude/incoming/`. **Nothing is written to the portal repo yet.** If the ticket has multiple units, the agent asks you to pick one.

**Step 2 — generate the Page Object code (in your Playwright repo)**

Switch to your Playwright repo and run:

```
> /add-test
```

or say: `把推过来的场景形成用例`

The `add-test` pipeline reads the incoming spec, validates selectors against the live app, and generates Page-Object-style Playwright code that fits the existing suite conventions (`pages/`, `fixtures/`, naming rules). **Nothing is pushed automatically** — review the diff and `git push` yourself.

---

## Project layout

```
.claude/
  agents/                # sub-agents only: linear-fetcher, test-triage, test-data-planner, test-strategist
  runbooks/              # in-context runbooks: test-executor, linear-reporter (read by orchestrator, not spawned)
  skills/                # /test-tickets, /archive-to-portal, /sync-test-cases, /create-case, /switch-account, /toggle-feature-flag, /retro
  settings.json          # checked-in: permissions allowlist, MCP servers
  settings.local.json    # gitignored: per-developer paths, secrets
  # test credentials now live in config/env.stg.json, env.prod.json, env.ca.json (repo root)
chrome-proxy/
  proxy_server.py        # MCP proxy: multiplexes chrome-devtools-mcp across isolated Chrome sessions (one per session_id)
  pyproject.toml
artifacts/               # gitignored: per-run outputs
fixtures/
  manifest.json          # checked-in: fixture name → Drive file id mapping
  cache/                 # gitignored: downloaded PDFs
prompts/
  linear-comment-template.md  # single source of truth for Linear comment format
  strategy-template.md        # Requirement Spec template for test-strategist
  triage-rules.md             # deterministic triage rules for test-triage
schemas/                 # JSON Schemas for spec / trace / result
scripts/
  attach-screenshot-to-comment.py   # compress + upload + delete attachment shim
  check-phase.py                    # orchestrator pre-flight between phases
  get-fixture.py                    # name → cached file via Drive API
  google-drive.py                   # OAuth client + find/download
  validate-artifact.py              # schema validator
  verify-mcp.sh                     # tracker MCP OAuth bootstrap
docs/
  SETUP.md
CLAUDE.md                # operating manual the agents read on every session
```

## Hard rules at a glance

- **No silent skips.** Every skipped ticket has a written reason. Every acceptance criterion must map to a scenario in the spec — even when it requires a different user role than the unit's default (the executor switches accounts mid-run via `/switch-account`).
- **Default to fresh test data.** If a unit needs specific data shape, the planner creates a new case with the right fixtures rather than hunting through the existing case pool. Reuse only when the user/spec names a case explicitly or the change is data-free.
- **Spec is grounded in PR diffs, not ticket prose.** When the ticket promises X but the PR doesn't ship X, that's an Open question, not a scenario.
- **No reload during a scenario unless the spec demands it.** Reload destroys evidence of "things that should update live but didn't"; that class of bug needs an explicit non-reload observation first.
- **No production writes outside the test tenant.** Credentials configured per-env in `config/env.prod.json` and `config/env.ca.json`.
- **Feature flags and data gates are classified, not guessed.** The strategist runs a three-pass scan of every linked PR diff to separate localStorage-override flags (handled by `/toggle-feature-flag`) from data gates like `job_meta.ai_first` (handled by case-creation). Conflating the two causes silent test failures.
- **Tracker-side relationships are the human owner's job.** This agent posts comments and nothing else — never `relatedTo` / `blocks` / `parentId`. Some trackers (e.g. Linear) auto-create "related issue" backlinks from any ticket-id text in a comment body, so cross-ticket workflow context stays in local `05-summary.md`, never in the comment.

Full operating manual for agent-side rules: **[CLAUDE.md](./CLAUDE.md)**.

---

## Contributing

This is an early-stage POC, but PRs are welcome. A few notes before you start:

- **Treat the agent contract as the API.** Each sub-agent's `.md` file in `.claude/agents/` is a prompt _and_ a contract — change them deliberately and update `schemas/` if the artifact shape moves.
- **Don't add new schemas casually.** Hand-offs through schema-validated JSON are how we keep the pipeline debuggable. Prefer extending an existing schema to inventing a parallel one.
- **No real customer data in fixtures.** `fixtures/manifest.json` is checked in; the underlying PDFs live in a Drive folder you control. Fixtures committed to this repo must be either synthetic or already-public sample documents.
- **Open an issue first for big changes.** "Big" = new agent, new skill, schema breaking change, or anything that touches Linear/GitHub write semantics.

Bug reports and small fixes can go straight to a PR.

## License

TBD.
