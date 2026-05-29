# Radix Checkbox / Switch — CDT MCP Interaction Limitation

## Problem

`button[role="checkbox"]` and `button[role="switch"]` components built with `@radix-ui/react-checkbox` or `@radix-ui/react-switch` do **not** respond to CDT MCP click interactions. Specifically:

- The click lands on the element (accessibility tree confirms focus)
- React's synthetic event system does NOT fire
- `data-state` remains `"unchecked"` / `"off"` — state does not toggle
- Attempted workarounds that **do not work**: `element.click()`, `React fiber onClick`, `__reactProps.onClick`, `onCheckedChange(true)`, Space key via `press_key`

## Root cause (observed)

Radix UI Checkbox uses a Tooltip wrapper `span[data-state]` above the button, and the component is built in "controlled" mode — the checkbox is driven by external React state. CDT MCP click dispatches a CDP `Input.dispatchMouseEvent` that reaches the DOM but does not bubble through React's event delegation layer at the `document` level, so the controlled state setter is never called.

## The executor rule

**Cap at 2 CDT MCP `click` attempts, then mark `fail`.** Do not proceed to JS approaches. See `.claude/runbooks/test-executor.md` → **Known-unreliable interaction types**.

## Signals that identify this component type

- `button[role="checkbox"]` with `data-state="unchecked"` or `data-state="checked"`
- Often wrapped in `<span data-state="closed">` (Radix Tooltip)
- Class contains `rounded-[2px]` (DS checkbox border radius) or `place-content-center peer`
- Parent row is a `<tr>` in a DS Table (`data-slot="table-row"`)

## Known occurrences

| Component | Surface | First seen |
|-----------|---------|-----------|
| `ConnectorDocumentSyncTreeV2` | Create Case wizard Step 3 — file selection checkboxes | DOC-3344 (2026-05-27) |

## Manual verification workaround

When the executor marks this blocked, the QA note in the Linear comment should direct the reviewer to:
1. Open the portal in Chrome manually
2. Navigate to the same surface
3. Click the checkbox with a real mouse click
4. Confirm whether `data-state` changes to `"checked"`

If it does in manual testing → CDT MCP limitation (not a product bug).  
If it does NOT → product bug in the Radix Checkbox event handler.
