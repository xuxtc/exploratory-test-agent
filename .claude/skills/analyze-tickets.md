---
name: analyze-tickets
description: Analyze Linear tickets and produce bilingual (Chinese + English) E2E test case tables — without executing tests or writing to any external system. Usage: `/analyze-tickets SUP-7152[,SUP-7497,...]`. Trigger phrases: "分析 XXX", "分析一下 XXX", "analyze tickets XXX". Accepts both ticket IDs and Linear URLs.
---

# /analyze-tickets

You are analyzing Linear tickets to produce structured E2E test case tables. This skill does **not** execute tests, does not write to Google Sheets, and does not post to Linear — output stays in the conversation.

## Arguments

- Ticket IDs (required): comma-separated ticket IDs (e.g. `SUP-7152,SUP-7497`) or Linear URLs (e.g. `https://linear.app/supio/issue/SUP-7849/...`). Extract the ticket ID from any Linear URL before proceeding.

If no IDs are provided, ask for them before proceeding. Do not invent ticket IDs.

The user may trigger this with natural language. All of the following are equivalent:
- "分析 SUP-7152"
- "分析一下 SUP-7152, SUP-7497"
- "帮我分析一下这几个票 SUP-7152 SUP-7497"
- "分析 https://linear.app/supio/issue/SUP-7849/publish-econ-when-archiving-the-case"
- "analyze tickets SUP-7152"
- "analyze SUP-7152,SUP-7497"

## Pipeline

### Step 1 — Fetch tickets and PR diffs

Resolve the exploratory-test-agent root:
```bash
REPO_ROOT=$(git rev-parse --show-toplevel)
AGENT_ROOT="$REPO_ROOT/exploratory-test-agent"
if [ ! -d "$AGENT_ROOT" ]; then
  echo "ERROR: Cannot locate exploratory-test-agent/ under repo root $REPO_ROOT. Abort."
  exit 1
fi
```

Generate a run-id and create an artifacts directory:
```bash
RUN_ID=$(date +%Y-%m-%d_%H%M)_<first-ticket-id>
mkdir -p "$AGENT_ROOT/artifacts/$RUN_ID"
```

Invoke the `linear-fetcher` sub-agent with the ticket list and run-id. It will write:
- `artifacts/<run-id>/01-fetch.json`
- `artifacts/<run-id>/01-pr-diffs.json`

Wait for it to complete before proceeding.

### Step 2 — Read context files and run feature flag audit

Read these files to inform your analysis:
- `$AGENT_ROOT/context/feature-flags/index.md` — known flags registry
- `$AGENT_ROOT/context/portal-routes/index.md` — surface → route mapping (if the file exists)

Then run the **feature flag audit** before writing any test case. This is mandatory and not skippable.

#### Feature flag audit (3 passes)

**Pass 1 — Scan diff for explicit flag references.**
Grep the `patch` fields in `01-pr-diffs.json` for patterns like `feature-[a-z0-9-]+`, `featureFlagStore`, `isXxxEnabled`, `isDrafterDefault`, `enabledFeatureFlags`. Collect every candidate flag name.

**Pass 2 — Cross-reference with context index.**
For each candidate flag found in Pass 1:
- If it is already in `context/feature-flags/index.md` → use it normally.
- If it is NOT in the index → this is a newly discovered flag. Add it to `context/feature-flags/index.md` and create a stub `context/feature-flags/<flag-key>.md` with the information you can derive from the diff, then use it in test cases. Do not silently drop it.

**Pass 3 — Check for nav-gating flags not present in the diff.**
A feature flag that controls a Left Nav entry or a top-level route will NOT appear in the PR diff — it lives in the nav component, which this PR did not touch. These flags are the most likely to be missed.

Apply this check: if the diff adds or rewrites a significant portion of files under a named module directory (e.g., `app-v2/caseload/`, `app-v2/ledger/`, `app-v2/tasks/`), look up whether that module has a nav-gating flag:
1. Search `context/feature-flags/index.md` for a flag matching the module name.
2. If found → include it in all test case preconditions.
3. If NOT found → output a visible warning block before the test table:

   ```
   ⚠️ Nav-gating flag not confirmed
   This PR rewrites the <module> module. Top-level UI modules in this portal are
   typically gated by a Left Nav feature flag (likely `feature-<module-name>`).
   No matching flag was found in the diff or context/feature-flags/index.md.
   Action required: confirm the flag name with the developer or check the Left Nav
   source before testing. Add it to context/feature-flags/index.md once confirmed.
   ```

   Do NOT silently assume "no flag needed" or mark the feature untestable without surfacing this warning.

### Step 3 — Analyze and produce output

Read `artifacts/<run-id>/01-fetch.json` and `artifacts/<run-id>/01-pr-diffs.json`. For each ticket, read its PR diff (the `patch` fields) and ticket description together before writing anything.

**HARD RULE — produce the Strategy Brief before writing the bilingual table. This is not optional.** Answer the three questions below from the diff alone and write the Brief inline (it will appear in the output before the table). The bilingual table is blocked until the Brief is written. Each field may be `"None"` — missing signal is fine; fabricating signal is forbidden.

**① Core business flow**: 1–3 sentences on user entry point → key action(s) → observable outcome (the happy-path spine). Degrade gracefully:
- Pure bugfix: describe what the user saw before vs. now.
- Style-only diff with no logic change: write `"Cannot be inferred from diff"` and skip ② and ③.
- Fragmented refactor: describe the aggregate user-visible effect.

**② Key thresholds / state boundaries**: scan for numeric constants in comparisons, state-machine labels/enums, idempotency guards, timeout/retry values, pagination cut-offs. Format: `<name>: <value> → edge test point`. Write `"None"` if absent.

**③ Risk areas / blind spots**: check each category — skip any with no diff evidence:
- Permission boundary (role-conditional rendering)
- Data state dependency (feature gated on case/job state)
- Concurrent / side-effect (mutation visible in another component or polling loop)
- Failure / degradation path (error handling, empty-state, retry logic)
- Irreversible operations (delete, archive, submit, terminal state)

Write `"None identified"` if none apply.

Use the Brief to drive test point design: ① → primary test points; ② and ③ items with diff evidence → edge test points; items without diff evidence → excluded (note in the table as "no diff evidence").

For **each ticket**, output both language versions back-to-back before moving to the next ticket.

---

#### Per-ticket output format

**`[TICKET-ID]` — [ticket title]**

---

##### 🇨🇳 中文版

**实现了什么**

2–4 句话从用户视角描述该 ticket 实现的功能，不涉及技术实现细节。

**策略分析**

- **核心业务路径**：<用户入口 → 操作 → 结果，1–3 句；如无法从 diff 推断写"无法推断，退化为 AC 驱动">
- **关键指标 / 状态边界**：<阈值、状态转换等，格式 `名称: 值 → 边界测试点`；无则写"无">
- **风险盲区**：<有 diff 证据的风险类别（权限边界 / 状态依赖 / 并发副作用 / 异常降级 / 不可逆操作）；无则写"无">

**E2E 测试用例（仅 UI 层）**

| 序号 | Test Point | 前置条件 | Test Steps | Expected Result | Test Result |
|------|-----------|---------|-----------|----------------|------------|
| 1 | （简洁描述测试目标） | 登录账号类型、需开启的 Feature Flag（仅引用 `context/feature-flags/index.md` 中已有的 flag）、数据准备要求等；如无特殊条件写"无" | 1. 步骤一 2. 步骤二 3. 步骤三（如步骤涉及 AI 提示词，直接给出可复制粘贴的原文） | 5. 用户应看到的结果 7. 另一个预期结果 | Pass |

**Test Steps 格式规则**：步骤之间用空格分隔，直接连写（如 `1. 步骤一 2. 步骤二 3. 步骤三`），不使用 `<br>` 或任何 HTML 标签。

**Expected Result 格式规则**：若预期结果与特定步骤编号对应，直接用步骤编号开头（如 `5.` 而不是 `步骤 5：`）；多条预期结果之间用空格分隔，直接连写（如 `5. 结果一 7. 结果二`）。

---

##### 🇺🇸 English Version

**What it implements**

2–4 sentences describing the feature from a user perspective, no implementation details.

**Strategy Brief**

- **Core business flow**: <entry point → action(s) → outcome, 1–3 sentences; write "Cannot be inferred from diff" if not applicable>
- **Key thresholds / state boundaries**: <format `name: value → edge test point`; write "None" if absent>
- **Risk areas**: <risk categories with diff evidence (permission boundary / data state / concurrent side-effect / failure path / irreversible op); write "None identified" if absent>

**E2E Test Cases (UI layer only)**

| # | Test Point | Preconditions | Test Steps | Expected Result | Test Result |
|---|-----------|--------------|-----------|----------------|------------|
| 1 | (concise test objective) | Login account type, feature flags required (from Step 2 flag audit — diff scan + context index + nav-gating check), data setup; write "None" if no special conditions | 1. Step one 2. Step two 3. Step three (if a step requires an AI prompt, include the exact copy-pasteable text inline) | 5. What the user should see at step 5 7. What the user should see at step 7 | Pass |

**Test Steps format rule**: separate steps with a single space — write them inline (e.g. `1. Step one 2. Step two 3. Step three`). Do not use `<br>` or any HTML tags.

**Expected Result format rule**: when a result corresponds to a specific step number, lead with the step number (e.g. `5.` not `Step 5:`); separate multiple results with a single space (e.g. `5. Result one 7. Result two`).

---

### Step 4 — Write machine-readable output

Write `$AGENT_ROOT/artifacts/$RUN_ID/00-analyze-output.json` — this file is the contract between `/analyze-tickets` and the downstream `test-strategist`. When `/test-tickets` is run against the same ticket(s) and finds this file, strategist will consume it directly instead of redesigning scenarios from scratch.

Schema:
```json
{
  "run_id": "<run-id>",
  "analyzed_at": "<ISO-8601>",
  "tickets": ["TICKET-1"],
  "scenarios_by_ticket": {
    "TICKET-1": {
      "strategy_brief": {
        "core_flow": "<1–3 sentence happy-path description, or 'Cannot be inferred from diff'>",
        "thresholds": ["<name>: <value> → edge test point"],
        "risk_areas": {
          "permission_boundary": "<description or null>",
          "data_state_dependency": "<description or null>",
          "concurrent_side_effect": "<description or null>",
          "failure_degradation": "<description or null>",
          "irreversible_operations": "<description or null>"
        }
      },
      "scenarios": [
        {
          "id": 1,
          "title": "<concise scenario title>",
          "kind": "primary | edge",
          "given": "<precondition>",
          "when": "<exact user action or agent prompt text>",
          "then": "<observable outcome>",
          "related_acs": [1, 2],
          "feature_flags": ["feature-case-agent"],
          "out_of_scope_reason": null
        }
      ],
      "out_of_scope": [
        {
          "title": "<scenario title>",
          "reason": "<why excluded — backend validation / unit test / non-UI / no diff evidence>"
        }
      ]
    }
  }
}
```

Rules:
- Every scenario shown in the bilingual table must appear in `scenarios_by_ticket` — no silent omissions.
- Every item excluded from the table must appear in `out_of_scope` with an explicit reason.
- `when` for Case Agent scenarios must include the exact prompt text (copy-pasteable), matching what was written in the Test Steps cell.

### Step 5 — Summary

After writing the file, print:
```
Analyzed N ticket(s): TICKET-1, TICKET-2, ...
Scenario output written to artifacts/<run-id>/00-analyze-output.json — run /test-tickets with the same ticket IDs to execute directly from this analysis.
```

## Hard rules

- **PR diff is mandatory.** Do not produce test cases from ticket title or description alone. Both `01-fetch.json` and `01-pr-diffs.json` must be read first. If a ticket has no associated PR, produce best-effort cases from the description with a visible warning.
- **Scenario coverage rules (shared).** Before writing test points, read `context/testing-scope/scenario-coverage-rules.md`. It defines three hard rules that apply to every skill that designs scenarios from a ticket+diff: (1) one test point per code entry point, (2) PR reported issue → E2E test point, (3) CTA side-effect isolation. All three are mandatory here.
- **UI layer only.** Every test step must be navigable by a human tester in a browser. No API-level, unit-test, or backend-only points.
- **Prompts must be copy-pasteable.** If a step requires an AI prompt (e.g. for Case Agent or Demand Agent), provide the exact prompt text inline in the Test Steps cell — not a placeholder like "enter a prompt".
- **Feature flags — verify, don't invent; but actively discover.** The source of truth for flag names is the diff scan (Pass 1) + context index (Pass 2) + nav-gating check (Pass 3) from Step 2's feature flag audit. Do NOT invent flag names that appear in neither the diff nor the codebase. But DO actively discover flags via the three-pass audit — "it's not in the index" is not a reason to omit a flag; it is a trigger to add it to the index.
- **Cover all test points, stay concise.** Merge related assertions into one row rather than splitting into many thin rows.
- **No external writes.** Do not call `mcp__linear__save_comment`, do not write to Google Sheets, do not post to Slack.
- **Always output both languages.** Never produce only one language version for a ticket.
