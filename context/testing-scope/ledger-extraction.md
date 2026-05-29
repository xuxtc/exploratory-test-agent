# Ledger Extraction — Testing Scope Rules

## When this rule applies

Any ticket that touches the **Ledger** tab, bill/lien extraction, line item display, or the agent-managed ledger write path.

---

## 1. V1 vs V2 Pipeline — Identify Before Planning Scenarios

The system has two extraction pipelines. Which one a case uses determines the expected behavior, status polling, and DB output.

| | V1 | V2 (default for new cases) |
|---|---|---|
| Indicator | `job_meta.ledger_version` absent or `!= 'v2'` | `job_meta.ledger_version = 'v2'` |
| Chunk logic | Whole document in one LLM call | AI detects bill boundaries → splits into chunks (`BillChunkCreator`) |
| Supported subtypes | Bills, BillsWithAP, HICF, EOB, PharmacyBill, LienBill | All V1 types + APOnly, HealthInsuranceLien, AutoInsuranceLienPIP/Medpay, OtherLien, NonItemizedFinancial, LienLetter |
| Re-extract path | Not available | `POST /v1/financial-records/case/:caseId/reextract-with-ap` — **deletes all existing line items first** |

**Testing implication:** When a ticket mentions re-extraction, A&P mode, or lien extraction, it targets V2 only. Verify `ledger_version = 'v2'` in the test case's `job_meta` before executing those scenarios.

---

## 2. Extraction Trigger Types

### Auto-trigger (AI-first case)
Fires automatically after document classification when:
- `job_meta.ai_first = true`
- Case type is "Simple SI"
- Document has extractable financial pages

No user action needed. The pipeline sets `extracted_to_ledger: true` in `job_meta` and runs in the background.

### Manual trigger (user adds bills)
User clicks **Add Bills** → selects documents → `POST /v1/financial-records/document-jobs/add`.

Both paths produce the same pipeline: Classification → VLM OCR → Bill chunk extraction → DB write → Embeddings → Dedup.

---

## 3. Extraction Status Flow

Frontend polls every 3 seconds until terminal state:

**Case-level** (`GET /v1/financial-records/case/:caseId/status`):
```
uploading → classifying → extracting → normalizing → completed | timed_out
```

**Per-document** (`GET /v1/financial-records/case/:caseId/document-statuses`):
```
pending → classifying → extracting → completed | timed_out | failed
```

When verifying extraction scenarios, check that:
- Status transitions happen in order (no skips to `completed` without passing through `extracting`)
- `timed_out` and `failed` documents surface a dismissible entry in the Generation Panel
- Line items refresh automatically when `completedCount` increases

---

## 4. Agent-Managed Ledger (`agent_controlled_artifacts`)

Some tickets involve the **agent-managed ledger** path — where a Claude agent (not the standard pipeline) writes bills/liens into the ledger.

### The gate
Agent ledger write tools (`upsert_ledger_record`, `upsert_ledger_line_items`) check:
```
jobs.job_meta.agent_controlled_artifacts === true
```
If the flag is missing, the agent returns: *"This case does not use the Agent Package ledger."*

### How to enable on an existing case

**The `document_group_job_update` GraphQL mutation does NOT set this flag** — the field is silently ignored by the API (verified: passing `agent_controlled_artifacts: true` in `job_meta` input returns the response without the field).

The only working methods are:
1. **Direct DB patch** (needs DB access):
   ```sql
   UPDATE jobs
   SET job_meta = job_meta || '{"agent_controlled_artifacts": true}'::jsonb
   WHERE id = <case_id>;
   ```
2. **Create the case via the agent `create_case` tool** — it automatically spreads `AGENT_CONTROLLED_ARTIFACTS_META` at creation time.

### Testing implication
When a ticket tests agent-driven ledger generation:
- Confirm the test case has `agent_controlled_artifacts: true` in its `job_meta` **before** running the scenario
- If not set, the test cannot proceed via UI/API alone — escalate to a DB patch or use a pre-configured test case
- Do NOT mark the scenario FAIL because of this missing flag; log it as a **[Blocker]** precondition gap and skip the scenario

---

## 5. Instant Ledger (Beta) — MT Case Type Coverage (SUP-7742)

The Instant Ledger (IL) Beta view is now available on **all Mass Tort (MT) case types** in the pre-v2 (non-Case Agent) UI.

### Coverage history

| Phase | Case types with IL Beta |
|-------|------------------------|
| Before SUP-7742 | Asbestos + one other MT type; Simple SI; Complex SI |
| After SUP-7742 | **All MT case types** + Simple SI + Complex SI |

### Key constraints

- **No automated extraction**: Opening the Ledger tab on an MT case must NOT trigger any extraction pipeline. The Beta IL view loads in a static display state.
- **Beta label required**: A "Beta" badge/label must be visible on the IL view for all MT cases.
- **Pre-v2 only**: This change applies to the pre-v2 view (`feature-case-agent` = OFF). The Case Agent (app-v2) path is unaffected.

### Feature flag required

`feature-ai-artifact-first` = ON — without this flag the Instant Ledger surface does not render.

### Testing implications

- To test the new behavior, use an MT case type that was NOT previously supported (e.g., NEC — the designated MT test case type per [mass-torts-case-type.md](mass-torts-case-type.md)).
- Always include an Asbestos case as a regression check alongside any newly-enabled type.
- Verify scope boundary: a non-MT case (e.g., Simple SI) opened under the same flag state must NOT show the IL Beta view.
- If the Ledger tab shows any extraction status indicator after opening, that is a defect — log it as a violation of the "no automated extraction" constraint.

---

## 6. AI Ledger / Instant Ledger / Billing / Econ Sidebar Visibility (SUP-7745)

In the legacy timeline shell (`TimelineSideNavbar` + `useCaseNavItems`), which tabs appear in the left sidebar is gated **solely** on `job_meta.ai_first`. The org-level `feature-ai-artifact-first` flag no longer participates in this decision (removed as of SUP-7745).

### Truth table

| # | `ai_first` | `isAiLedgerEnabled` (flag) | Main nav "AI Ledger" | Beta nav "Instant Ledger" | Billing / Econ |
|---|---|---|---|---|---|
| ① | true | ON | ✅ | — | hidden |
| ② | true | OFF | ✅ (same as ①) | — | hidden |
| ③ | false | ON | — | shown (if `isInstantLedgerEnabled`) | shown |
| ④ | false | OFF | — | shown (if `isInstantLedgerEnabled`) | shown |

### What changed — two bugs fixed

- **Bug A** (`ai_first=false` + flag ON): Previously showed "AI Ledger" in main nav and hid Billing/Econ. Now correctly shows "Instant Ledger" in BETA section with Billing/Econ visible.
- **Bug B** (`ai_first=true` + flag OFF): Previously dropped "AI Ledger" from the nav. Now still shows "AI Ledger" in main nav.

### Lien education popover

The lien education popover (and its backing queries `checkDismissed` / `getViewCount`) only fires for `ai_first=false` cases on the Instant Ledger path. AI-first cases ("AI Ledger") never trigger the popover.

### Testing implications

- Use an AI-first case (`ai_first=true`) to validate scenarios ① and ②.
- Use any historical MT case (`ai_first=false`) to validate scenarios ③ and ④ — all MT case types now qualify for Instant Ledger (see Section 5, SUP-7742).
- To confirm both bug fixes, toggle `feature-ai-artifact-first` ON and OFF within the same test session:
  - Flag **OFF** + AI-first case → "AI Ledger" must still appear (validates Bug B fix)
  - Flag **ON** + historical MT case → "Instant Ledger" must appear in BETA, NOT "AI Ledger" (validates Bug A fix)
- The "non-eligible historical case shows no ledger" scenario (Workbench) no longer applies to MT cases after SUP-7742. Do not include it as a regression check for MT-type cases.

---

## 7. Key API Endpoints for Ledger Test Scenarios

| Purpose | Endpoint |
|---------|----------|
| Add documents to ledger | `POST /v1/financial-records/document-jobs/add` |
| Poll case extraction status | `GET /v1/financial-records/case/:caseId/status` |
| Poll per-document status | `GET /v1/financial-records/case/:caseId/document-statuses` |
| Fetch extracted line items | `GET /v1/financial-records/case/:caseId/line-items-v2` |
| Re-extract with A&P (V2 only) | `POST /v1/financial-records/case/:caseId/reextract-with-ap` |
| Check pre-A&P re-extract gate | `GET /v1/financial-records/case/:caseId/pre-ap-status` |
| Remove failed document | `POST /v1/financial-records/document-job/:documentJobId/remove-from-ledger` |
| Trigger unrelated charge analysis | `POST /v1/financial-records/cases/:caseId/analyze-unrelated-line-items` |
| Push ledger to Salesforce/Litify | `POST /v1/connectors/pushback/case/:caseId` (`artifacts: ['facility_ledger']`) |
