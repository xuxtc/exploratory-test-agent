# Business Rule: Drafting AI documents via agent chat

## When this rule applies

Any test scenario that exercises the AI document drafting feature in the Portal agent chat — including but not limited to:

- Demand Letter
- Complaint
- Disclosure
- Settlement letter
- Any other document type available via the agent chat draft flow

## What it controls

### Prompt pattern

To trigger the draft flow in agent chat, use the following prompt pattern:

```
Draft a <document type> using files from the Knowledge Base <document type> folder.
```

**Examples:**

| Document type | Prompt |
|---------------|--------|
| Demand Letter | `Draft a demand letter using files from the Knowledge Base demand letter folder.` |
| Complaint | `Draft a complaint using files from the Knowledge Base complaint folder.` |
| Disclosure | `Draft a disclosure using files from the Knowledge Base disclosure folder.` |

Replace `<document type>` with the exact document name as it appears in the Portal UI.

### What to assert

After sending the prompt, verify:

1. The agent responds without an error or timeout.
2. A draft document is generated and displayed (non-empty content).
3. The document type matches the requested type (check title or header in the output).
4. The content references case-relevant information drawn from the Knowledge Base files (not generic placeholder text).

### What NOT to assert

- Do **not** assert exact wording, paragraph structure, or legal phrasing — AI output is non-deterministic.
- Do **not** fail the scenario if the draft is lengthy; length alone is not a defect.
- Do **not** compare output across runs — each generation may differ.

## Test case

Use the following designated case for all draft document tests:

- **Case URL:** `https://portal.supio.com/cases/8420645/ledger`
- **Case ID:** `8420645`
- **Environment:** prod

Navigate to this case before opening agent chat and sending the draft prompt. Do not create a new case or switch to a different case unless the ticket explicitly requires it.

## Known interactions

- The Knowledge Base folder for the requested document type must be populated before the prompt is sent. If the folder is empty, the agent may refuse or produce a generic response — this is expected behavior, not a bug.
- If the ticket specifies a particular document type, use that exact type in the prompt. If the ticket is generic ("test the draft feature"), default to Demand Letter as the representative case.
