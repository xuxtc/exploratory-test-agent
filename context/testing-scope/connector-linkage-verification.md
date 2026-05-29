# Connector Linkage Verification Rule

## Two categories of connectors

Supio has two distinct connector types that require different verification approaches:

- **CMS (Case Management System)** — Litify, Salesforce, SmartAdvocate, GrowPath, Filevine, GhostPractice. Linked to a case via `create_case` tool's `connector_id` + `external_case_id` args. Verified at two levels (see below).
- **DMS (Document Management System)** — OneDrive, Dropbox, ShareFile, SharePoint, GoogleDrive, Box. Surfaced as tabs in the Upload Files dialog. No matter ID required — verification is whether the tab appears and can browse files.

**Important:** DMS connectors cannot be passed as `connector_id` to `create_case`. The Agent will reject them. Only CMS connectors are valid `connector_id` values.

---

## When this rule applies

Any test scenario that verifies connector linkage — either CMS case linkage via `create_case`, or DMS file access via the Upload Files dialog.

---

## CMS connector verification (two levels required)

Verifying `job_meta.connector` fields via GraphQL is **necessary but not sufficient**. A complete CMS connector linkage test must verify both:

### Level 1 — Data layer
Query `job_meta.connector` via GraphQL `document_group_job`:
```graphql
query { document_group_job(id: <case_id>) { id job_meta } }
```
Confirm `job_meta.connector.name` and `job_meta.connector.external_id` are written correctly.

### Level 2 — UI layer
1. Navigate to the agent-created case detail page.
2. Click "Upload Case Files" (top-right of Case Files panel).
3. Verify the connector's tab (e.g. "Litify", "SmartAdvocate") appears in the Upload Files dialog alongside DMS tabs.
4. Click the tab — verify it shows files/folders from the linked external matter.

### Priority
| Connector | Priority |
|-----------|----------|
| Litify | **Must verify — FAIL if not working** |
| SmartAdvocate | **Must verify — FAIL if not working** |
| Filevine, Salesforce, GrowPath, GhostPractice | Log as `[Product]` finding if not working |

---

## DMS connector verification

1. Navigate to any case detail page.
2. Click "Upload Case Files".
3. Verify the connector's tab appears in the dialog.
4. Click the tab — verify it can browse files from the DMS (no matter ID needed).

### Priority
| Connector | Priority |
|-----------|----------|
| OneDrive | **Must verify — FAIL if not working** |
| Dropbox | **Must verify — FAIL if not working** |
| ShareFile, SharePoint, GoogleDrive, Box | Log as `[Product]` finding if not working |

---

## Dedup pitfall — use a fresh matter ID per run

When verifying CMS connector linkage, always use a matter ID that has **not** been linked to any existing Supio case. If the matter ID was used in a prior run, `create_case` will trigger dedup (refuse to create a duplicate) and no new connector-linked case will be created — the Upload Files dialog will then show no connector tab, which looks like a product failure but is actually expected dedup behavior.

**How to detect:** If the Agent responds with "a case already exists for that matter" rather than "case created", dedup fired. Choose a different matter ID and re-run.

Verified working (DOC-3422, 2026-05-25): Litify and SmartAdvocate connector linkage both correctly surface the connector tab in the Upload Files dialog when a fresh (unused) matter ID is supplied.

---

## Known product gap — DMS connectors not supported in create_case (DOC-3422)

`create_case`'s `connector_id` parameter currently only accepts CMS connectors (Litify, Salesforce, SmartAdvocate, GrowPath, Filevine, GhostPractice). DMS connectors (OneDrive, Dropbox, ShareFile, etc.) are rejected by the Agent.

This is a product gap, not intentional design — the AC does not explicitly exclude DMS connectors. When DMS support is added in a future ticket, it will require:
1. Accepting DMS `connector_id` values in `create_case`
2. A new no-`external_case_id` scenario — DMS connectors have no matter ID concept, so the current "both-or-neither" mutual-presence rule (`connector_id` + `external_case_id` must both be present or both absent) will need to be revised to allow `connector_id`-only for DMS connectors.

When a ticket ships DMS connector support, verify both changes above.

## Reference
- `context/test-accounts/connector-matter-ids.md` — CMS matter IDs + DMS connector list
