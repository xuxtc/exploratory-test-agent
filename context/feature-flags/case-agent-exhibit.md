# feature-case-agent-exhibit

**Flag key:** `feature-case-agent-exhibit`  
**Gates:** Exhibit feature within the Case Agent UI (app-v2)

## When to require this flag

Enable `feature-case-agent-exhibit` whenever:
- The ticket involves the Exhibit feature inside the Case Agent page
- Any changed file in the PR relates to exhibit functionality under app-v2

## What it controls

`feature-case-agent-exhibit` activates the Exhibit surface inside the Case Agent UI. It is a sub-flag of `feature-case-agent` — both must be ON for Exhibit to be accessible.

## Required flag combination

Testing Exhibit in the Case Agent page requires **both** flags enabled:

| Flag | Purpose |
|------|---------|
| `feature-case-agent` | Activates the app-v2 Case Agent UI shell |
| `feature-case-agent-exhibit` | Activates the Exhibit surface within that shell |

If either flag is off, the Exhibit entry point will not appear. Do not mark this as a bug — verify both flags are on before starting the scenario.

## Known interactions

- `feature-case-agent` must be verified first. If it is off, `feature-case-agent-exhibit` has no effect.
- Use `/toggle-feature-flag` to enable both flags before navigating to the Case Agent page.
