# Browser Interactions — Index

Techniques for driving browser interactions that the Chrome DevTools MCP accessibility-tree driver cannot trigger natively. Consult the relevant detail file when a spec scenario requires one of these interaction types.

| Interaction | When to use | Detail file |
|---|---|---|
| `dnd-kit` drag-and-drop | Any scenario requiring drag-reorder on a component built with `@dnd-kit/core` + `PointerSensor` (e.g. `SortableFreshList`, any list with `aria-label="Drag to reorder"` handles) | [dnd-kit-drag.md](dnd-kit-drag.md) |
| Panel collapse / expand | Any scenario requiring collapse or expand of a panel whose header is a `div[role="button"]` rather than a `<button>` (e.g. `TodaysWorkPanel` My Focus header) | See rule below — standard `click` is sufficient, no special script needed |
| Radix Checkbox / Switch | `button[role="checkbox"]` or `button[role="switch"]` built with `@radix-ui/react-checkbox` / `@radix-ui/react-switch` — CDT MCP click lands but React state does not update. Cap at 2 CDT MCP click attempts; mark `fail` with manual-verification note. | [radix-checkbox.md](radix-checkbox.md) |

## Panel collapse / expand — no special script needed

When a spec scenario requires collapsing or expanding a panel:

1. **Don't assume the trigger is a `<button>`.** React panels often use `div[role="button"]` on the header to avoid nested-button HTML violations (e.g. when a `<button>` already exists inside the header for a sub-control like a period menu).
2. **Find the element by `aria-expanded`.** In the a11y tree snapshot, look for an element with `aria-expanded="true"` or `aria-expanded="false"` — that is the collapse toggle, regardless of its HTML tag.
3. **Click it directly.** The Chrome DevTools MCP `click` tool works on any element with `role="button"`, including `div[role="button"]`. No PointerEvent simulation needed.

**Example (TodaysWorkPanel):**

```
// In a11y tree: uid=X_Y generic role="button" aria-expanded="false" "My Focus ..."
// Click uid to expand; click again to collapse.
```

After clicking, assert by checking that `aria-expanded` flipped and that the panel content is visible / hidden accordingly.
