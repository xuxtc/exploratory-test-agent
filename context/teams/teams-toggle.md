# Teams Toggle

## Where to find it

Log in as the company's FIRM_ADMIN, then navigate to **Settings → Teams**. The toggle to enable/disable teams is on this page.

- **ON**: teams feature is enabled for the company (`limit_case_visibility=true` in the backend)
- **OFF**: teams feature is disabled

### How to check / change the teams toggle before a test run

1. Log in as the `team` account (FIRM_ADMIN on "QA Test Team Company")
2. Navigate to: **Settings** (left nav) → **Teams** tab
3. The page shows the current toggle state. If teams is OFF and the scenario requires it ON, flip the toggle and confirm the change.
4. **Always restore the toggle to its original state after testing** to avoid affecting other testers.

> **Pre-run checklist for teams-related tickets**: Before executing any scenario that branches on `limit_case_visibility`, open Settings → Teams and screenshot the current state. This confirms the precondition and provides evidence if the test result is unexpected.

## What it controls

### Create Case / Update Case

When teams = ON, the **Create Case** form shows a **Teams** field with "Default Team" pre-selected (see screenshot evidence from SUP-7784 testing). When teams = OFF, the Teams field is absent from the form entirely.

This means: any ticket that touches teams-related logic must include a **Create Case or Update Case** scenario to verify that the Teams field appears/disappears correctly based on the toggle state.

## Test implications

- To verify teams ON behavior: ensure the company has teams enabled before running the scenario. Navigate to Settings → Teams and confirm the toggle is ON.
- To verify teams OFF behavior: turn the toggle OFF first, then attempt to create/edit a case and confirm the Teams field is not shown.
- **Always restore the toggle to its original state after testing** to avoid affecting other testers.

## Which test account to use

- Use the `team` account (FIRM_ADMIN on **"QA Test Team Company"**) for prod teams testing.
- "QA Test Team Company" has teams configured and is the designated test company for teams-related scenarios.
