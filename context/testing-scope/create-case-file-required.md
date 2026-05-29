# Business Rule: Create Case files are optional (bare-case creation supported)

## When this rule applies

Any test scenario that exercises the Create Case form (`/create-case`) in the app-v2 shell (`feature-case-agent` on), specifically when testing the submit/create action.

## What it controls (current behavior — post APP-2987)

Files are **optional** when creating a case. The Create button is enabled even with zero files uploaded.

- Observing the Create button **enabled with no files** = **expected, PASS**
- Completing case creation with no files and landing on a "Case created successfully!" completion screen = **expected, PASS**
- Do NOT mark bare-case creation as a FAIL or flag it as a product gap

## What changed

**APP-2987 (merged 2026-05-13)** fixed a regression where `Step3FileUpload` called `setStepValid(false)` when no files were present, inadvertently disabling the Create button. The fix passes `disableUpdateStepValid` to Step 3 so the wizard sets `isStepValid(true)` after advancing to the upload step. The completion screen now shows "Case created successfully!" via a new `bare_case_created` state instead of the perpetual upload-in-progress message.

The underlying bare-case API path (`createCase({ documents: [] })`) always existed in `CaseCreatePage.tsx`; APP-2987 made the UI path reach it.

## Previous behavior (pre APP-2987 — no longer applies)

Before APP-2987, the button was disabled until at least one file was added (`documents.length > 0`). This was documented as "intentional" during run `2026-05-12_1433_DOC-3144` — that documentation is now superseded by this ticket.

## Source

APP-2987 merged 2026-05-13. PR #10423 author comment: ryan.furuyama@supio.com.
