# How to upload a file to an existing case (no UI file picker)

## When this rule applies

Any test scenario that needs to add a new file to an already-created case in order to trigger a new AI pipeline cycle — e.g. re-testing `reviewing`, `review_stale`, or `review_completed` states that require a fresh extraction run.

## Why NOT to click "Upload files" or the `+` button in CASE FILES

The "Upload files" button and the `+` icon in the CASE FILES sidebar both open a **native OS file picker dialog**. The native picker cannot be dismissed or operated programmatically via Chrome DevTools MCP. Clicking either button will block the run until a human manually clicks Cancel. **Never click these buttons during an automated run.**

## Correct method: API upload (3 steps)

All three steps run via `evaluate_script` — no UI interaction required.

### Step 1 — Get presigned S3 URL

```js
const uploadKey = `documents/cases/Test Company/<caseName>/<uniqueFileName>.pdf`;
const r = await fetch('https://api.supio.com/api/v1/uppy/s3', {
  method: 'POST', credentials: 'include',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ key: uploadKey })
});
const { url: presignedUrl } = await r.json();
```

- `caseName` is the job's `name` field (e.g. `deqtest_sup7708_timeline-status`)
- Use a **unique filename** (e.g. append `_cycle2_<timestamp>`) to avoid S3 key collision with existing files
- The key prefix `documents/cases/Test Company/` is the `job_meta.case_key` — fetch it via GraphQL if uncertain (see below)

### Step 2 — PUT file to S3

```js
// Fetch from CORS server (must be running on port 8765)
const fileBlob = await fetch('http://localhost:8765/<filename>.pdf', { mode: 'cors' }).then(r => r.blob());
await fetch(presignedUrl, {
  method: 'PUT',
  headers: { 'Content-Type': 'application/pdf' },
  body: fileBlob
});
```

### Step 3 — Register file with backend via `document_addToJob`

```js
const r = await fetch('https://api.supio.com/api/v1/ext', {
  method: 'POST', credentials: 'include',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    query: `mutation addDocumentToJob($input: DocumentAddToJobInput!) {
      document_addToJob(input: $input) { id status }
    }`,
    variables: {
      input: {
        document: { key: uploadKey, size: fileBlob.size },
        document_group_job_id: <caseId>,          // numeric case/job ID
        assigned_company_ids: <assignedCompanyIds> // array from job query
      }
    }
  })
});
const result = await r.json();
// result.data.document_addToJob.status should be "ANNOTATION_PENDING"
```

This call registers the document in the DB and **triggers the AI pipeline** (status transitions to `extracting`).

## How to get `case_key` and `assigned_company_ids` for an unknown case

```js
const r = await fetch('https://api.supio.com/api/v1/ext', {
  method: 'POST', credentials: 'include',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    query: `query($search: String) {
      document_group_jobs_v2(search: $search) {
        list { id name assigned_company_ids job_meta }
      }
    }`,
    variables: { search: '<caseName>' }
  })
});
const job = (await r.json()).data.document_group_jobs_v2.list[0];
// job.job_meta.case_key  →  "documents/cases/Test Company/<caseName>"
// job.assigned_company_ids  →  [27, 91, 136]  (for the external test tenant)
```

## Verification

After `document_addToJob` returns:
1. Poll `/api/v1/folders/<caseId>` — new file should appear in `folder.documents`
2. Poll `/api/v1/ai-first-timeline-generation-status/<caseId>` — status should change from `empty` / `review_completed` to `extracting`
3. Reload Medchron page — status panel should render with "Updating your timeline / Extracting N timeline files"

## Anti-patterns

- ❌ Clicking "Upload files" button — opens native OS file picker, blocks the run
- ❌ Clicking the `+` icon in CASE FILES sidebar — same problem
- ❌ Calling `document_updateUploadState` without first calling `document_addToJob` — the mutation returns `false` because no document record exists yet
- ❌ Reusing the same filename as an existing file — S3 PUT succeeds but `document_addToJob` may create a duplicate record or silently fail

## Source

Discovered during SUP-7708 run `2026-05-15` when the reconcile step needed to re-trigger the pipeline on an existing case. Verified: `document_addToJob` → `ANNOTATION_PENDING` → pipeline status `extracting` → panel visible on page reload.
