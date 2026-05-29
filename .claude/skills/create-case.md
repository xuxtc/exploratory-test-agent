---
name: create-case
description: Create a new test case in the Supio prod/stg portal via the /create-case UI, with fixture file upload. Supports local files (default) or connector source. Usage: /create-case [case-name] [--type <case-type>] [--env prod|stg] [--files <f1.pdf,f2.pdf>] [--connector <name>]. Drives the browser via Chrome DevTools MCP using upload_file for file upload.
---

# /create-case

You drive the Supio portal's `/create-case` flow to create a new AI-artifact-first test case end-to-end. The user invokes this when a test scenario needs a brand-new case in a known starting state — typically when the spec's Data setup says "create a new case named `deqtest_<topic>_<run-id>` and upload fixtures".

This skill is **deterministic and quiet**: it does not ask the user to pick fixtures or case type unless they explicitly override defaults. The defaults below are what a typical AI-artifact-first scenario needs.

## Argument

- `[case-name]` (optional): the Case name field. If omitted, derive a sensible one — for ad-hoc invocations use `deqtest_create-case_<timestamp>`; if the user is mid-`/test-tickets` run, use `deqtest_<ticket-id-lowercase>_<run-id>` (e.g. `deqtest_sup-7623_2026-05-08_1524`).

## Defaults (apply unless user overrides)

| Field | Default | Why |
|---|---|---|
| Connector | **No connector** | Strips the Case ID requirement and avoids touching external systems (Litify, Filevine, etc.). |
| File source | **Upload from my computer** | Local upload is the most reliable path; cloud-source flows depend on connector auth. |
| Case type | **MVA** | Most AI-first scenarios on the test tenant use MVA. Stage auto-fills. |
| Demand letter | **none** | Not needed unless a scenario explicitly asserts on demand-flow behavior. |
| Fixtures | **`Police Report.Pdf` + `MRnMB.pdf`** | These two together cover incident, medical-record, medical-bill, and treatment event types — enough for the AI-first pipeline to produce a non-empty `timelineDocumentIds[]` and exercise extracting → postprocessing → empty. Both live in the team's `Supio QA` shared drive under the `AUTO/` subfolder. |

The default fixture list lives in `fixtures/manifest.json`. The two defaults are pulled from the team's `Supio QA` shared drive (folder `0ABN1KXZHE2OUUk9PVA`, subfolder `AUTO` = `1-KrKSmynJ_KhqSYstEttxrw6RnqHsmDq`). Update `manifest.json` when the canonical names change — the skill reads names from there.

### Google Drive setup (first-run, per machine)

`get-fixture.py` downloads via Drive API using OAuth, not public links — the Drive content is access-controlled. First time you run `/create-case` on a fresh machine you need:

1. `.claude/google-oauth-client.json` — Desktop OAuth client config from GCP Console. See README's "Google Drive setup" section.
2. Run once: `scripts/google-drive.py auth` — opens the browser, asks you to grant `drive.readonly` to the OAuth client. The token caches to `.claude/google-oauth-token.json` (gitignored, mode 0600). Refresh-token flow takes over after that — you won't see the browser again unless you revoke access in your Google account settings.

If `get-fixture.py` returns `{"ok": false, "stage": "drive_helper_failed", "exit_code": 4, ...}` it means the cached token is missing — re-run the `auth` step.

If the spec under test asserts on event types those two fixtures do **not** cover (e.g. `wage_loss`, a stand-alone `medical_bill`, an `imaging` study), add the relevant fixture to the upload set:
- Read `scripts/get-fixture.py --list` to see what's pre-mapped in the manifest.
- If the needed type isn't pre-mapped, add a new entry to `fixtures/manifest.json` (Drive file id + `covers_event_types`) and let the script pull it. Don't hard-code Drive ids inside this skill.

## Optional flags

- `--with <fixture-name>[,<fixture-name>...]` — replace the default fixture set with this list. Each name must exist in `fixtures/manifest.json`. Example: `/create-case deqtest_x --with "Incident_Report.pdf,MedicalRecords.pdf,bill UMPC.pdf"`.
- `--add <fixture-name>[,<fixture-name>...]` — keep defaults and append these. Example: `/create-case deqtest_x --add "bill UMPC.pdf"` to add a discrete medical-bill event on top of the defaults.
- `--type <case-type>` — override the case type (e.g. `--type "Premises Liability"`). Default MVA.
- `--no-demand-letter` (default; included only for explicitness) / `--with-demand-letter` — currently the form has no demand-letter checkbox under the No connector + manual upload path, so `--with-demand-letter` is informational.

## Pre-flight

Before any browser action:

1. The Chrome DevTools MCP is connected (the test-tickets pipeline should already have set this up; if invoked standalone, call `mcp__chrome-devtools__list_pages` first to confirm).
2. The user is signed in to `https://portal.supio.com` as the external test account (Supio Test). If `/create-case` redirects to login, fail with a clear "log in via the test-env credentials, then re-run" error rather than attempting to log in here — auth is the test-executor's job, not this skill's.
3. Resolve every fixture name to a local cached path:

   ```bash
   scripts/get-fixture.py --name "<fixture-name>"
   ```

   If a fixture isn't in cache, the script downloads it from Drive into `fixtures/cache/<name>.pdf`. The script's stdout is one line of JSON; parse it. On `ok: false` with `stage: download_returned_non_pdf`, fall back to asking the user to drop the PDF into `fixtures/cache/` manually, then retry. **Don't try to scrape Drive's UI yourself — the script handles that path or fails clearly.**

## File upload — `upload_file` via CDP (the ONLY allowed method)

> **STOP. READ THIS BEFORE ANY FILE UPLOAD ACTION.**
> The one and only allowed upload method is `mcp__chrome-devtools__upload_file` after unhiding the Uppy input.
> Do NOT use DragEvent simulation, base64 injection, or any local HTTP server — those approaches
> are unreliable in the VSCode extension environment and have been retired.

The portal uses Uppy with a hidden `<input type="file" class="uppy-DragDrop-input">`. The `upload_file` tool uses Playwright's `handle.uploadFile()` which goes through CDP's `DOM.setFileInputFiles` — this bypasses the OS native file picker entirely, sets files directly on the element, and triggers Uppy's internal `change` handler automatically. No browser security restrictions apply.

**The input is `hidden` by default and does not appear in the a11y snapshot.** Unhide it first so it gets a uid, then call `upload_file` once per fixture:

```js
// Step 1 — unhide the input (evaluate_script):
() => {
  const input = document.querySelector('.uppy-DragDrop-input');
  input.removeAttribute('hidden');
  input.style.cssText = 'display:block;position:static;width:1px;height:1px;';
  return { done: true };
}
```

```
// Step 2 — take_snapshot to get the uid of the now-visible input
// It appears as: button "Choose Files" value="No file chosen"
```

```
// Step 3 — upload_file once per fixture (uid stays stable across uploads):
mcp__chrome-devtools__upload_file(uid="<uid>", filePath="<absolute-path-to-fixture>")
```

Repeat Step 3 for each fixture. After each `upload_file` call, the file immediately appears in Uppy's file list with its correct name and size. No `change` event dispatch needed — Playwright handles this internally.

**After all fixtures are uploaded**, verify via snapshot or screenshot that the file list shows the expected count and sizes, and that **Total: N files** matches.

## Workflow

1. **Announce**: `Creating case "<resolved-case-name>" with fixtures [<list>] (type=<type>, no connector).`
2. Ensure fixture files are cached: `scripts/get-fixture.py --name "<fixture-name>"` for each.
3. Navigate to `https://portal.supio.com/create-case`. Confirm page load via `take_snapshot` (look for "Drop here" in the drop zone button text).
4. Fill **Case name** via React native setter:
   ```js
   () => {
     const input = document.querySelector('#caseName');
     Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(input, '<name>');
     input.dispatchEvent(new Event('input', { bubbles: true }));
   }
   ```
5. Set **Case type** by typing into `#caseType`, then clicking the matching `.ant-select-item-option` (the option list appears after typing).
6. **Upload fixtures** (see section above):
   - `evaluate_script` to unhide `.uppy-DragDrop-input`.
   - `take_snapshot` to get the input's uid (shows as `button "Choose Files"`).
   - `upload_file(uid, filePath)` once per fixture — the uid remains stable across all uploads.
   - After all uploads, take a screenshot to confirm files appear in the list with correct filenames and sizes.
7. Click **Create case** via `evaluate_script`:
   ```js
   () => Array.from(document.querySelectorAll('button')).find(b => b.textContent?.trim() === 'Create case')?.click();
   ```
8. Poll `location.href` until it leaves `/create-case`. Then find the case ID:
   ```js
   async () => {
     const r = await fetch('https://api.supio.com/api/v1/cases/search?limit=1&q=<case-name>', { credentials: 'include' });
     return (await r.json())?.list?.[0]?.id;
   }
   ```
9. Navigate to `https://portal.supio.com/cases/<case-id>/events`. Wait for files to appear in CASE FILES sidebar.
10. Navigate to `/cases/<id>/medical-chronology`. Wait for extracted events or a **"View N new files"** button to appear. If "No events found" and files are in CASE FILES sidebar: yield via `ScheduleWakeup` for 90s and re-poll; cap at 20 min. Do NOT check the Events tab (`/cases/<id>/events`) — that shows case-level events, not extraction results. Do NOT use `/api/v1/cases/<id>/event-count` — always returns 0. (The Overview tab has been removed.)
11. Return: `Created case <case-id> "<case-name>" with N fixtures. Extraction status: <complete|in_progress|unknown>.`

## Hard rules

- **Never invent ticket / case ids.** If `case-name` resolution depends on a ticket id and the user didn't pass one, ask once. Do not autopopulate from "the most recent run" — that has bitten us before with the wrong case.
- **Test tenant only.** The flows here write to prod. The test account `user@test.supio` lives in an isolated tenant per `CLAUDE.md`'s test-environment rule; never invoke this skill while signed in as a real internal user.
- **Don't ask the user to pick fixtures by default.** Defaults are good enough for AI-first scenarios; only prompt if (a) the user explicitly passed `--with` with names not in the manifest, or (b) `get-fixture.py` returned `ok: false` and the user needs to drop a file manually.
- **Don't hardcode Drive file ids inside this skill or the script's caller.** All ids live in `fixtures/manifest.json`; the manifest is the contract.
- **Case kind determines the V2 timeline, not a localStorage feature flag.** `TimelinePage.tsx` gates `ArtifactFirstTimelineV2` purely on `job_meta.ai_first` — a data property set by the backend at case-creation time based on case kind. Creating the case as "AI-artifact-first MVA" is what sets this; `/toggle-feature-flag` cannot substitute for it. Note: `feature-ai-artifact-first` *does* exist as a flag (it gates the AI Ledger label and some file-approval components), but it does NOT gate the V2 timeline mount — `TimelinePage.tsx` explicitly has no flag check ("No feature flag — the job_meta value is the contract").

## Anti-patterns

- ❌ **DragEvent simulation** — previously used but retired. It relied on a local HTTP CORS server (`http://localhost:8765`) which is blocked by Mixed Content policy when the portal runs on HTTPS in the VSCode extension environment. Do not resurrect this approach.
- ❌ **Base64 injection via `evaluate_script`** — the 1–4 MB base64 strings for real fixture PDFs exceed the MCP tool call payload limit. Not viable.
- ❌ **Local CORS server** (`python3 /tmp/cors_server.py`) — no longer needed. Do not start one.
- ❌ Calling `upload_file` without unhiding the input first — the hidden input has no uid in the snapshot and the call will fail with "element not found".
- ❌ Calling `upload_file` with a path outside the workspace roots — the MCP server rejects paths under `~/Downloads`, `/tmp`, `~/Desktop`, etc. Fixture files must be under the project directory (`exploratory-test-agent/fixtures/cache/`).
- ❌ `Object.defineProperty(input, 'files', ...)` + manual `change` event — the files are empty at the time the event fires (CDP hasn't written them yet). Use `upload_file` instead.
- ❌ Reading the Drive folder's HTML / a11y tree to enumerate files — that path is fragile, virtualized, and language-locale-dependent. Use the manifest.
- ❌ Falling back to "any PDF will do" if a manifest fixture isn't downloadable — the AI-first pipeline needs real medical-shaped content to produce non-empty `timelineDocumentIds[]`. A junk PDF will give you a case stuck at `status: 'empty'` and no panel.
- ❌ Filling Case ID under the No-connector path. That field is hidden by the form when `connector === none`; trying to interact with it crashes the snapshot.

## Extending the manifest

When a future PR introduces a new event type the defaults don't cover:

1. Find the right fixture in the team Drive folder (`https://drive.google.com/drive/u/0/folders/1-KrKSmynJ_KhqSYstEttxrw6RnqHsmDq`). Note its file id from the URL when you click into the file.
2. Add an entry to `fixtures/manifest.json` with `drive_file_id` + `covers_event_types`.
3. Run `scripts/get-fixture.py --name "<new-name>"` once to seed the cache.
4. Update the **Defaults** table above only if the new fixture should be part of the *default* set — otherwise just leave it in the manifest and let scenarios opt into it via `--with` / `--add`.
