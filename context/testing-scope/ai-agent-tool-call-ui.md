# AI Agent Tool-Call UI — Testing Scope

Some UI components in the Chat Area are only rendered when the AI backend emits a specific tool call response. These **cannot be triggered via a predictable prompt** — the AI autonomously decides whether to call the tool based on session state, connector availability, and internal reasoning.

## Known tool-call UI components

| Component | Tool call | Required session state | First seen |
|-----------|-----------|----------------------|-----------|
| `FileTreeToolCall` | `present_file_tree` | Active case-agent session; case has a linked connector with accessible files | DOC-3344 (2026-05-27) |

## Executor rule — 1 attempt, then blocked

When a scenario depends on a tool-call UI component:

1. **Open a fresh case-agent session** for the case (per the Fresh AI session rule in the executor runbook). Do NOT reuse an existing session.
2. **Send 1 prompt** designed to elicit the tool call (e.g. "Sync connector files into this case"). Wait as long as the AI needs — no timeout. Do not send a second rephrased prompt.
3. **Check for the widget.** If it appeared → proceed with the scenario.
4. **If it did not appear** → mark the scenario `fail`:
   ```
   fail_reason: "AI-triggered tool call [tool-call-name] not emitted after 1 attempt — manual verification required. AI responded but did not emit the expected tool call."
   ```
5. Take a screenshot of the chat showing the AI's response (proves the attempt was made).

## Strategist rule — always medium confidence

When a spec unit targets a tool-call UI component:
- Set `data_confidence: medium` on **all** scenarios in the unit.
- In `data_blocker`, document: (a) which tool call is required, (b) what session/case state is needed, (c) the suggested prompt.

## Data-planner rule — check session state feasibility

If the unit's primary surface is a tool-call UI component, check:
- Does the test account have a case with a linked connector?
- Is the case accessible from the test account?

If neither condition can be met, set `case_decision: blocked_no_fixture` with `fixture_gap` naming the required tool call, connector type, and session state.

## Why "1 attempt, no retry"

AI tool call emission is probabilistic and session-state-dependent. A second rephrased attempt after the AI already responded without the tool call is almost never productive — the AI has already made its routing decision for that context. Human intervention (checking connector linkage, verifying case state, testing manually in the browser) is more productive than more prompts.
