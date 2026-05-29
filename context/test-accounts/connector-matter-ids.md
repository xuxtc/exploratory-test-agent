# Connector Test Data

Connectors in Supio fall into two distinct categories with different test approaches.

---

## CMS Connectors (Case Management Systems)

Used with `create_case` tool's `connector_id` + `external_case_id` args to link a new Supio case to an external matter at creation time. Available on `user@test.supio` prod external account.

| Connector | `connector_id` value | `external_case_id` | Priority |
|-----------|----------------------|--------------------|----------|
| Litify | `Litify` | `a0LV4000007Dfm7` | **Must verify** |
| SmartAdvocate | `SmartAdvocate` | `4` | **Must verify** (note: `32` was used in a prior run and is already linked; use `4` as backup) |
| SmokeballDirect | `smokeballdirect` | (linked via case 8770066 — `deqtest_smoke_ball_case_jolly_05_26_01`) | Use case 8770066 for `get_case_status`; matter = Kent, Clark (MVA Plaintiff, Status: Open, opened 2026-05-05) |
| Filevine | `Filevine` | `987654321` | Finding if not working |
| Salesforce | `Salesforce` | TBD | Finding if not working |
| GrowPath | `GrowPath` | TBD | Finding if not working |
| GhostPractice | `GhostPractice` | TBD | Finding if not working |

**Note:** Dropbox, OneDrive, ShareFile, SharePoint, GoogleDrive, Box are **DMS connectors** (document storage), not CMS connectors — they cannot be passed as `connector_id` to `create_case`. The Agent will reject them and list the valid CMS connectors.

### Usage rules

- **One matter ID per connector per run.** Do not reuse the same `external_case_id` across runs without confirming prior linkage was cleaned up — if a case already exists for that matter, `create_case` will trigger dedup.
- **Create before operate (Rule 4).** Scenarios that verify connector linkage must sequence: (1) create the linked case, (2) verify linkage in the same session.
- **Cover must-verify connectors first.** If time-constrained, prioritize Litify and SmartAdvocate; flag remaining as findings.

### ConnectorDocumentSyncTreeV2 — CMS vs DMS feature gating

The Create Case wizard Step 3 renders different columns in `ConnectorDocumentSyncTreeV2` depending on connector type. **Identification rule: CMS connectors require a matter ID (`external_case_id`) when linking; DMS connectors do not.**

| Feature | CMS connectors | DMS connectors |
|---------|---------------|----------------|
| Per-folder Auto Sync switch (Sync column) | ❌ Not shown | ✅ Shown |
| "Synced to Supio" column | ❌ Not shown | ✅ Shown |
| DMS lazy folder loading | ❌ Not shown | ✅ Shown |
| Checkbox file selection | ✅ Shown | ✅ Shown |
| Search filter | ✅ Shown | ✅ Shown |

**Implication for test-data-planner:** When a spec unit tests `showSyncColumn`, `showSyncedToSupioColumn`, or per-folder Auto Sync, verify a DMS connector is configured on the test account. If only CMS connectors are available, set `case_decision: blocked_no_fixture` with `fixture_gap: "DMS connector required (OneDrive/Dropbox/etc.) — only CMS connectors available on this account"`.

---

## DMS Connectors (Document Management Systems)

Surfaced as tabs in the **Upload Files dialog** on a case detail page. These are for uploading/syncing documents, not for linking a case to an external CMS matter.

| Connector | Upload Files tab name | Priority |
|-----------|-----------------------|----------|
| OneDrive | `OneDrive` | **Must verify** |
| Dropbox | `Dropbox` | **Must verify** |
| ShareFile | `ShareFile` | Finding if not working |
| SharePoint | `SharePoint` | Finding if not working |
| GoogleDrive | `GoogleDrive` | Finding if not working |
| Box | `Box` | Finding if not working |

### How to verify DMS connectors

1. Navigate to a case detail page.
2. Click "Upload Case Files" (top-right of Case Files panel).
3. Check that the connector's tab appears in the Upload Files dialog.
4. Click the tab — verify it connects to the actual DMS and lists available files/folders.

### Known issue (DOC-3422, 2026-05-25)

Cases created via `create_case` with `connector_id="Litify"` show **no Litify tab** in the Upload Files dialog, even though `job_meta.connector` is written correctly at the data layer. Human-created Litify cases correctly show the Litify tab. This is a known product gap — see `context/testing-scope/connector-linkage-verification.md`.
