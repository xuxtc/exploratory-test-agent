# bug-scenario-coverage

## When this rule applies

When testing a **bug fix ticket** where the original bug required specific data conditions (e.g. a case with corrupted/invalid field values, a case belonging to a non-whitelisted company, a specific backend state that cannot be reproduced in the test tenant).

## What it controls

The test agent must **distinguish between two coverage levels** and communicate both clearly in the Linear comment:

1. **General-scenario coverage** (automated): the fix does not break existing functionality under normal data conditions. This is what the executor can always verify.
2. **Original bug scenario** (may require manual verification): the exact data condition that triggered the original bug. If this cannot be constructed in the test environment, it must be explicitly called out — not silently omitted.

## Required action when original bug scenario is not coverable

Add a `[Info]` bullet to `### Notable findings` in the Linear comment that states:

- What the original bug condition was (e.g. "a case whose extracted events contain an unparseable date value")
- Why it cannot be covered (e.g. "the affected cases belong to a non-whitelisted company and cannot be accessed under prod safety rules", "no fixture produces this data shape")
- What manual verification step is needed (e.g. "navigate to one of the affected cases after confirming the prod deploy", "ask the engineer to confirm against a known-bad case")

**Do not post a PASS result without this caveat** — the reader will assume full coverage including the bug scenario.

## Example finding

```
- **[Info]** Above scenarios used a freshly created test case with normal fixture data.
  The original bug requires a case whose extracted events contain an unparseable date value —
  the affected prod cases belong to a non-whitelisted company and cannot be accessed under
  prod safety rules. The fix on those specific cases needs manual verification by someone
  with access to that company, or by navigating to one of the affected cases after confirming
  the prod deploy.
```

## What NOT to do

- Do not omit `### Notable findings` just because all scenarios passed — if coverage is partial, findings are required.
- Do not attempt to access non-whitelisted companies to cover the bug scenario — prod safety rules take precedence.
- Do not mark the ticket as "fully tested" in comments or status changes.
