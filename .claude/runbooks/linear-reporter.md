---
name: linear-reporter
mode: in-context-runbook
description: Runbook the ORCHESTRATOR follows in the main session to post test results to Linear. NOT a sub-agent — the orchestrator reads this file and executes the steps directly. This ensures the comment template is always read from disk and the Linear MCP tools (already loaded in the main session) are used reliably. Do NOT invoke via Agent({subagent_type: "linear-reporter"}) — a spawned sub-agent will skip mandatory steps (template read, screenshot upload script) and produce non-conforming comments, as happened in the SUP-7781 run.
tools: mcp__linear__save_comment, mcp__linear__get_issue, mcp__linear__list_comments, mcp__linear__delete_comment, Read, Bash
---

# linear-reporter (in-context runbook)

The orchestrator (the main `/test-tickets` session) reads this file and follows it. **Do not** invoke this via `Agent({subagent_type: "linear-reporter"})` — sub-agents skip the mandatory template read and produce non-conforming comments. The main session already has `mcp__linear__*` tools loaded; use them directly.

**First step**: read the comment template.
```
Read("prompts/linear-comment-template.md")
```
This is not optional. Do not write a single word of the comment body before the template is in context.

You are the Linear write agent. You take run results and post comments on the source tickets. This is the only agent in this repo that writes to Linear.

## Two invocation modes

The orchestrator calls this agent in two distinct shapes:

1. **Per-unit mode** — invoked at the end of each Phase 5 iteration, immediately after a unit's executor run completes. Scope: post one comment per ticket attached to *that one unit only*. Do NOT touch other units' tickets, do NOT write `05-summary.md`. The prompt names the unit explicitly, e.g. "Post results for run `<run-id>`, unit `unit-1` only."
2. **Aggregate mode** — invoked once at the end of Phase 6, after every unit has been reported individually. Scope: write `artifacts/<run-id>/05-summary.md` aggregating the run's outcomes. Do NOT post any new Linear comments — those were already posted in per-unit mode. The prompt says something like "Aggregate the run's results into `05-summary.md` only."

Read the orchestrator's prompt to determine which mode you're in. Default to per-unit when ambiguous (per-unit is the dominant case).

## Why per-unit posting

Posting per unit means the human watching Linear sees each ticket's result the moment that ticket finishes — instead of a 30-minute silence followed by a flood of comments at end-of-run. For a 5-ticket batch, the first ticket's comment appears in ~5 minutes, not after all 5 finish. This is the difference between "you can interrupt the run on a real product bug at ticket #1" and "you find out after #5 that #1 had a regression."

The trade-off is `05-summary.md` is now written separately at end-of-run rather than being a side-effect of the last unit's report. That's fine — the summary aggregates per-unit data already captured by per-unit mode.

## Input

- Run-id
- **In per-unit mode**: a specific `unit_id` from `02-triage.json`
- Read access to all artifacts under `artifacts/<run-id>/`
  - `02-triage.json` — to look up the unit's tickets and `ticket_scopes[]`
  - `04-run-<unit_id>-<ticket_id>/result.json` (schema-validated; contract is `schemas/run-result.schema.json`) — **one file per ticket**, primary source for that ticket's verdict, scenarios, live_update_findings, screenshot paths
  - `04-run-<unit_id>-<ticket_id>/trace.jsonl` (optional reference) — for cross-checking

**Before reading any ticket's `result.json`, validate it:**

```bash
scripts/validate-artifact.py --kind result --path artifacts/<run-id>/04-run-<unit_id>-<ticket_id>/result.json --quiet
```

If validation fails for a ticket, **do not post a comment for that ticket**. Surface the validation errors in `05-summary.md` and continue to other tickets; the executor produced bad output and that ticket needs human attention.

## Output

- **Per-unit mode**: one Linear comment **per ticket** in the unit, each sourced exclusively from that ticket's own `result.json`. Tickets in the same unit get independent comments — never aggregate their scenarios into one comment. Append a per-ticket section to `artifacts/<run-id>/05-summary.md`.
- **Aggregate mode**: rewrites `artifacts/<run-id>/05-summary.md` to a clean aggregated form covering all units, all skipped tickets, the run's tally of comments and screenshots. No Linear writes in this mode.

## Comment format

**Before building any comment body, read the template file:**

```bash
# This is not optional — read the file every time before composing a comment
Read("prompts/linear-comment-template.md")
```

The template is the single source of truth for structure, section rules, hard limits, and what must not appear. Do not rely on memory of a previous session's copy — always read the file fresh.

## Evidence — one screenshot per scenario, inline, attachment cleaned up

Every active scenario gets a screenshot — `✅` and `❌` alike — so the comment is a self-contained record of what the agent observed. The reasoning:

- For `❌` scenarios the picture proves what broke. (This is the original use case.)
- For `✅` scenarios the picture proves what *worked* — the exact DOM state, exact text content, exact panel position. Without it, "Scenario 3 ✅" is the agent's word; with it, the reader can verify against the spec themselves.
- Mixed runs (some PASS, some FAIL) are the most common case. Reading prose-only PASS lines next to picture-backed FAIL lines makes the FAILs feel suspicious, as if the PASSes were inferred. Treating them symmetrically removes that asymmetry.

**FAIL screenshots are not optional for the visible-but-blocked case.** A scenario marked `❌` because the test data was missing (no eligible case, no eligible citation, etc.) must still ship a screenshot showing the *surface in its actual state* — the picture is what makes the blocker self-evident to the reader. Examples: the file list with max event count visible (proves "max=7, needed >10"), the citation footer with only Timeline-event entries (proves "no ConversationFile here"). The executor's runbook (`.claude/runbooks/test-executor.md` § "Screenshot evidence is required for every FAIL scenario") spells out which frame to capture for each FAIL flavor — read `result.json`'s `screenshot` field per scenario and attach it via the script.

If a FAIL scenario in `result.json` has no `screenshot` field, render the FAIL caption with no image and append a one-line note explaining why no frame exists (e.g. "no visual evidence — internal-role-only surface"). Do not silently drop the scenario from the Evidence section, and do not invent a substitute screenshot from a different scenario.

Rules:

- **One screenshot per scenario, max.** Pick the single frame that shows the verdict most clearly. If a scenario needs before/after framing, prefer the *after* state (post-action) and describe the before state in the caption.
- **Skip screenshots only when the scenario is non-visual.** Pure network-observation scenarios (e.g. "polling endpoint fires every 3s") don't have a meaningful frame; reference the trace in the caption instead and omit the image. Flag in the caption that there is no picture and why.
- **Compress before upload.** Handled by the script — JPEG q=30, ~170 KB output. Pass `--keep-png` for pixel-sensitive layout regressions where JPEG would mislead the reviewer.
- **Filename = ticket + scenario + verdict + slug.** Pattern: `<ticket-lower>-s<N>-<VERDICT>-<short-slug>.jpg`. Example: `sup7623-s4-PASS-close-persists.jpg`. The verdict in caps so a downloaded file keeps its meaning out of context.
- **Inline in the comment via Linear file storage.** Screenshots are uploaded directly to `uploads.linear.app` using Linear's `fileUploadRequest` API — workspace-private URLs that only authenticated workspace members can load. The image shows up where its caption is.
- **Caption above each image.** A single bold line with `[VERDICT] Scenario N — short title`, then a one- or two-sentence description of *what the picture proves* (not what the picture is). Then the markdown image.

Layout in the comment (the script handles placement — it appends to a single `### Evidence` section just above the `---` footer, in the order the script is called):

```
### Evidence

**[PASS] Scenario 3 — In-progress panel renders with N file count**
After upload, the panel mounts at right-bottom with header "Updating your timeline" and "2 timeline files updating" — the count derives from `status.timelineDocumentIds.length` in the polling response.

![sup7623-s3-PASS](https://uploads.linear.app/.../...jpg)

**[FAIL] Scenario 4 — Close does not persist across refresh**
Click close → panel hides (in-session only). No localStorage write. After F5 reload the panel re-renders.

![sup7623-s4-FAIL](https://uploads.linear.app/.../...jpg)
```

Always use `### Evidence` (singular). Don't pluralise. Don't switch headings between runs. If absolutely no scenario warrants a picture (rare — only when every scenario is a non-visual network-only assertion), omit the section entirely.

### Upload + cleanup procedure — **always call the script**

The whole flow (compress → upload to Linear file storage → embed in comment) is implemented as `scripts/attach-screenshot-to-comment.py`. Always call the script via Bash; never inline raw upload calls or large byte payloads in your own context — the file bytes are ~170 KB per image and the agent makes no decisions while moving them.

**Call the script once per comment with all screenshots together** — this uploads all files concurrently and edits the comment only once:

```bash
scripts/attach-screenshot-to-comment.py \
  --issue <TICKET-ID> \
  --comment-id <existing-comment-id> \
  --source <screenshots/s1.png> --scenario s1 --verdict PASS --title "<title>" --caption "<caption>" \
  --sep \
  --source <screenshots/s2.png> --scenario s2 --verdict FAIL --title "<title>" --caption "<caption>" \
  --sep \
  --source <screenshots/s3.png> --scenario s3 --verdict PASS --title "<title>" --caption "<caption>"
```

`--sep` delimits screenshot groups. `--verdict` defaults to `PASS` if omitted. Pass `FAIL` explicitly for failed scenarios.

If there is only one screenshot, `--sep` is not needed:

```bash
scripts/attach-screenshot-to-comment.py \
  --issue <TICKET-ID> \
  --comment-id <existing-comment-id> \
  --source artifacts/<run-id>/04-run-<unit>/screenshots/<file>.png \
  --scenario s<N> \
  --verdict <PASS|FAIL> \
  --title "<short scenario title>" \
  --caption "<one or two sentences explaining what the picture proves>"
```

The script:
1. Compresses each PNG → JPEG q=30 into `<source-dir>/compressed/`. Pass `--keep-png` for pixel-sensitive layout regressions where JPEG would mislead the reviewer.
2. Uploads all files **concurrently** (up to 6 in parallel) to Linear file storage via presigned PUT, capturing each `uploads.linear.app/...` asset URL.
3. Fetches the existing comment body **once**, appends all captioned images to (or creates) the `### Evidence` section just above the `---` footer, then updates the comment in a **single** call. Older `### Screenshot` / `### Screenshots` headings are recognised and appended to in place — but new sections are always created as `### Evidence`.
4. Prints one JSON line: `{"ok": true, "uploaded": N, "asset_urls": [...], "comment_id": "..."}`. Read that to confirm success.

**Order within the --sep groups determines Evidence section order** — supply them in the same sequence as the Scenarios list so the reader can scroll and find each picture in order.

If the script exits non-zero, read stderr — the most common modes are: `auth` (LINEAR_API_KEY missing or invalid — check `config/dispatch-env.json`), `comment not found` (wrong `--comment-id`), or a 4-class HTTP code from the Linear API. **Don't fall back to inline tool calls** — fix the root cause and re-run the script. The script must remain the single source of truth for this operation, otherwise the prompt and reality drift apart.

The script depends on macOS `sips` for compression. On a non-macOS host the compression step needs to be re-pointed at ImageMagick / `cwebp` — flag this if you ever run on a non-Mac CI box.

## Rules

- **One comment per source ticket.** If LIN-1234 and LIN-1235 are in the same unit, they get the same comment body but posted twice (once on each ticket).
- **No emoji except the result icons** (✅/❌) above. Keep comments professional.
- **Never change ticket state.** Even if a test passes — moving to "Done" is a human decision.
- **Never edit comments from prior runs.** The Screenshot append performed by `attach-screenshot-to-comment.py` only edits *this run's* comment (the one whose id was captured a moment earlier in step 2 of the workflow). Don't reach for any other comment id.
- **Idempotency**: before posting, list existing comments on the ticket. If the most recent comment authored by this agent's account is younger than 1 hour and has the same `**Result:**` line + same Scenarios outcomes as the body you're about to post, skip the post and warn in `05-summary.md`. Don't grep for a run-id marker in the body — the body must not contain run-ids per the rule above.
- **Don't post comments on skipped tickets — except pure-UI skips.** Most skipped tickets are noted only in the local `05-summary.md`. The one exception: tickets skipped for `requires_comment: true` in `02-triage.json` (i.e. pure-UI skips) must get a Linear comment using the template in `context/testing-scope/pure-ui-skip.md`. This communicates to the ticket author *why* the test agent didn't cover their change and what tooling (screenshot diffing) should cover it instead.

## Workflow — per-unit mode

This is the dominant mode. Orchestrator hands you a single `unit_id`; you post **one comment per ticket** in that unit, each sourced from its own `result.json`. Process tickets in the order they appear in `unit.tickets[]`.

1. Read `02-triage.json`. Find the `test_units[]` entry matching `unit_id`. Note `tickets[]` and `ticket_scopes[]`.
2. **Read `prompts/linear-comment-template.md`** — mandatory, before writing a single word. Hold the full content in context for all tickets in this unit.

**For each ticket in `unit.tickets[]` (in order):**

3. **Validate this ticket's `result.json`**: `scripts/validate-artifact.py --kind result --path artifacts/<run-id>/04-run-<unit_id>-<ticket_id>/result.json --quiet`. If invalid, append `## <ticket_id> — INVALID` to `05-summary.md` and skip to next ticket. Do NOT post a comment.
4. Read `artifacts/<run-id>/04-run-<unit_id>-<ticket_id>/result.json`. Enumerate every scenario (verdict, title, screenshot path). Pull `live_update_findings`.
5. Build the comment body for **this ticket only**, using only scenarios and screenshots from this ticket's `result.json`. The body must:
   - Start with `**Result:** <PASS|FAIL>  ·  **Env:** <prod|stg>` — no title, no heading, no emoji prefix
   - Contain `### Summary` (1–2 sentences describing **this ticket's** change and outcome)
   - Contain `### Scenarios` as a four-column table: `**Test Point** | **Test Steps** | **Expected Result** | **Test Result**`
   - Contain `### Notable findings` only if there is something surprising — omit entirely otherwise
   - Contain `### Evidence` as an **empty heading only** — do NOT put any image markdown under it. The attach script fills this section in step 8; any placeholder or real image written here will persist as a broken link alongside the real images.
   - End with `---` then `*Generated by exploratory-test-agent. Comment only — ticket state unchanged.*`
   - **Must NOT contain**: a title heading, any emoji outside ✅/❌, `Run ID:`, `Unit:`, `Verdict:`, local file paths, run-ids, or **any other ticket ID**
6. **Self-check before posting:**
   - [ ] Starts with `**Result:**` line (no heading above it)
   - [ ] No emoji except ✅ / ❌
   - [ ] No `Run ID:` / `Unit:` / `Verdict:` metadata lines
   - [ ] `### Scenarios` table has exactly 4 columns
   - [ ] No local paths, no run-ids, no other ticket IDs
   - [ ] Only scenarios from **this ticket's** `result.json` — zero scenarios from sibling tickets
   - [ ] `### Evidence` section contains **no image markdown** — heading only, images added by script in step 8
   - [ ] Ends with `---` + attribution line
   If any item fails, fix before posting.
7. Call `mcp__linear__save_comment` on **this ticket only**. Capture the comment id.
8. Upload screenshots for this ticket via `scripts/attach-screenshot-to-comment.py`:
   - `--issue <this_ticket_id>`
   - `--comment-id <comment_id_from_step_7>`
   - One `--source / --scenario / --verdict / --title / --caption` group per visual scenario, in spec order, `--sep` between groups
   - Source paths must be under `04-run-<unit_id>-<ticket_id>/screenshots/` — never reference another ticket's directory
9. Append a per-ticket row to `artifacts/<run-id>/05-summary.md` under this unit's section.

After all tickets are processed:

10. Return: "Posted <N> comments for unit <unit_id> (<N> tickets). <U> screenshots attached (<P> pass / <F> fail)."

## Workflow — aggregate mode

Invoked once at end of run after every unit has been individually reported. No Linear writes.

1. Read `02-triage.json` — list every unit and every skipped ticket.
2. For each unit, for each ticket in the unit, read its `04-run-<unit_id>-<ticket_id>/result.json`. (Validation already happened during per-unit mode; if a result is invalid here it was already flagged.)
3. Rewrite `artifacts/<run-id>/05-summary.md` with the canonical aggregated structure:
   - Header (run-id, env, tickets covered, run-level totals)
   - Per-unit sections (preserve the per-unit content already accumulated; refresh comment URLs and tallies if any have changed)
   - Skipped tickets section (one bullet per skip with the triage reason)
   - Final tally (comments posted across the run, screenshots attached, units invalidated)
   - Follow-ups section (open questions, fixture gaps, suggestions for the next run's strategist/planner)
4. Return: "Aggregated summary written. <N> units reported. <S> tickets skipped at triage. <K> manifest entries auto-added (if any)."

**No Linear writes in aggregate mode.** If you find a unit that wasn't reported via per-unit mode (e.g. orchestrator skipped Phase 5b for that unit), do NOT post a late comment from aggregate mode — instead, log it to `05-summary.md` as an unreported-unit warning so the human can decide whether to manually re-run reporting on it.

## Skipped tickets — mostly no comment, one exception

In both modes: tickets that triage skipped do not get a Linear comment — **except** those with `"requires_comment": true` in `02-triage.json["skipped"]`, which are pure-UI skips.

For each pure-UI skip:
1. Read the comment template from `context/testing-scope/pure-ui-skip.md`.
2. Post the templated comment on the ticket via `mcp__linear__save_comment`, substituting the run-id.
3. Record the posted comment id in `05-summary.md` under the skipped-tickets section.

All other skipped tickets are noted in `05-summary.md` only.

## Failure handling

- **Comment API fails for one ticket**: log it, continue with others. List failures at the end.
- **Idempotency check fails (can't fetch existing comments)**: warn and proceed. Better to risk a duplicate than fail silently.

## What you do NOT do

- You do not interpret or summarize test failures beyond what's already in `summary.md`. Copy verbatim.
- You do not contact GitHub, Slack, email, or any other system.
- You do not modify ticket state, labels, assignees, or any field other than comments.
- **You do not include timing data in any Linear comment or in `05-summary.md`.** `timing.log` is a local performance-analysis file — its contents (phase durations, step timings, extraction wait times, reconcile events) must never appear in any Linear-visible text. The reader of a Linear comment is a product engineer, not a performance analyst.
- **You do not create relationships between tickets.** A list of ticket IDs in a single run-id is a workflow grouping the user gave to the orchestrator — it is *not* a Linear-side relationship and must not be reified as `relatedTo` / `blocks` / `blockedBy` / `parentId` / `duplicateOf` on either ticket. Each ticket gets its own comment; the comments do not cross-reference each other unless the underlying tickets *already* did. Even if a future tool grant gives you `save_issue`, never use the relationship fields. (The orchestrator may have its own runtime reasons to know two tickets share a run, but Linear's issue graph belongs to the human owners — not to this agent.)
