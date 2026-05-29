# Test Data Construction Strategy

## When this rule applies

Any ticket whose scenarios require specific event types that may not be present in extracted case data (e.g. Police Report, Medication, multi-facility medical records, Incident Report, specific procedure types).

## Rule: fixture-first, Add Event as fallback

Test data must be constructed in this priority order:

### Step 1 — Check fixtures/manifest.json first

Before writing scenarios, enumerate the event types each AC requires. Cross-check against `fixtures/manifest.json` using the `covers_event_types` annotations. For each required event type:

- If a fixture covers it → add that fixture to `fixtures_needed` in the data plan.
- If no fixture covers it → proceed to Step 2.

The strategist performs this audit in the `### AC coverage map` and records which fixtures satisfy which ACs.

### Step 2 — Add Event via UI (fallback only)

After case creation and extraction, if the extracted events still do not satisfy an AC's data condition (e.g. extraction did not produce a Police Report despite uploading a police report fixture), the executor may manually construct the missing data via the Medchron **Add Event** UI.

This is a valid fallback — not the first resort. The executor should:
1. Navigate to the case's Medchron tab.
2. Click **Add** to open the Add Event dialog.
3. Select the required event type, set the target date, set facility if needed (leave blank for null-facility scenarios), and save.
4. Verify the event appears in the timeline before proceeding with the scenario.

Manual events added this way are real writes against the test case — they persist. Name the test case with the `deqtest_` prefix so it stays within the write-allowed scope.

## Example (OPX-1415 sort rules)

OPX-1415 required: Police Report, Medication, Office Visit (two facilities), Office Visit (null facility), Imaging — all on the same date for sort-order verification.

No single fixture in `manifest.json` produced all of these on the same date. After uploading available fixtures and running extraction, the executor added 5 events via Add Event UI to October 1, 2008 on case `deqtest_real_case_05_15_01`. This produced a controlled, multi-type, multi-facility date group suitable for asserting all sort rules.

## What NOT to do

- Do not write a scenario and silently assume the extracted data will satisfy it.
- Do not mark a scenario PASS when the required data was absent — that is a trivially passing test, not evidence the feature works.
- Do not fall back to Add Event before checking `fixtures/manifest.json` — a fixture that produces the event type naturally is always preferred over manual construction.
