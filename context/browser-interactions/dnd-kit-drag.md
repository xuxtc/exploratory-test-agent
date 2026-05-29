# dnd-kit Drag-and-Drop Simulation

## When to use

Use this technique whenever a spec scenario requires drag-to-reorder on a component built with `@dnd-kit/core` + `PointerSensor`. Signals in the diff or a11y tree:

- Import of `PointerSensor`, `DndContext`, `SortableContext` from `@dnd-kit/*`
- Drag handle buttons with `aria-label="Drag to reorder"` (or similar)
- `roledescription="sortable"` on row elements in the a11y tree

**Do NOT use native `DragEvent` simulation** — dnd-kit explicitly prevents it (`window.addEventListener('dragstart', preventDefault)`). The correct approach is `PointerEvent` simulation.

## How dnd-kit PointerSensor works

- **Activation**: `onPointerDown` on the drag handle element (React synthetic event)
- **Move + end**: `pointermove` and `pointerup` listened on `document` (native, added after pointerdown)
- **Activation constraint** (typical): `{ distance: 4 }` — drag activates only after pointer moves > 4px

## Verified simulation sequence

```
1. pointerdown  → on handle element      (attaches dnd-kit document listeners)
2. pointermove  → on document, +6px y    (exceeds 4px distance constraint → drag activates)
3. pointermove  → on document, midpoint  (smooth trajectory)
4. pointermove  → on document, target    (positions drop target)
5. pointerup    → on document            (fires handleDragEnd → onReorder → PATCH API)
```

## Script (paste into `evaluate_script`)

```js
async function simulateDndKitDrag({ sourceIndex, targetIndex }) {
  const LABEL = 'Drag to reorder';
  const handles = Array.from(document.querySelectorAll(`button[aria-label="${LABEL}"]`));

  if (handles.length === 0)
    return { error: `No drag handles found with aria-label="${LABEL}"` };
  if (sourceIndex >= handles.length || targetIndex >= handles.length)
    return { error: `Index out of range — found ${handles.length} handles` };

  // Row text: handle → div → div (level 2 = row container with task name)
  function readOrder() {
    return Array.from(document.querySelectorAll(`button[aria-label="${LABEL}"]`))
      .map(h => {
        const row = h.parentElement?.parentElement;
        const text = row?.textContent?.trim() ?? '';
        return text.match(/^(deqtest_\S+?_\S+?_\S+?)(?:Supio|$)/)?.[1]
          ?? text.substring(0, 25);
      });
  }

  const src = handles[sourceIndex].getBoundingClientRect();
  const tgt  = handles[targetIndex].getBoundingClientRect();
  const sx = src.left + src.width/2,  sy = src.top + src.height/2;
  const ex = tgt.left + tgt.width/2,  ey = tgt.top + tgt.height/2;

  function ptr(type, x, y) {
    return new PointerEvent(type, {
      bubbles: true, cancelable: true,
      isPrimary: true, button: 0,
      buttons: type === 'pointerup' ? 0 : 1,
      pointerId: 1, pointerType: 'mouse',
      clientX: x, clientY: y, screenX: x, screenY: y,
    });
  }
  const delay = ms => new Promise(r => setTimeout(r, ms));

  const before = readOrder();

  handles[sourceIndex].dispatchEvent(ptr('pointerdown', sx, sy));
  await delay(60);
  document.dispatchEvent(ptr('pointermove', sx, sy + 6));   // exceed 4px constraint
  await delay(60);
  document.dispatchEvent(ptr('pointermove', sx, (sy + ey) / 2));
  await delay(60);
  document.dispatchEvent(ptr('pointermove', ex, ey));
  await delay(100);
  document.dispatchEvent(ptr('pointerup', ex, ey));
  await delay(300);  // allow React re-render to settle

  const after = readOrder();
  return {
    ok: true,
    handlesFound: handles.length,
    before,
    after,
    changed: JSON.stringify(before) !== JSON.stringify(after),
  };
}

// Example: drag item at index 0 to position of index 2
return await simulateDndKitDrag({ sourceIndex: 0, targetIndex: 2 });
```

## Assertion checklist

After calling `simulateDndKitDrag`, assert all three:

1. **`result.changed === true`** — React state updated, panel order changed
2. **dnd-kit screen reader announcement** — check a11y tree for `status` element containing `"Draggable item X was dropped over droppable area Y"`
3. **PATCH API call** — `list_network_requests` should show `PATCH /api/v1/task-lists/:id/items [200]`

For persistence-across-reload scenarios, reload the page after the drag and re-read the panel order.

## Important notes

- **Re-query handles after each drag** — React re-renders move DOM nodes, so stale handle references from before the drag will have wrong coordinates. Always re-query with `document.querySelectorAll(...)` fresh for each drag call.
- **Delay between consecutive drags** — if dragging multiple times in sequence, wait at least 300ms between calls to let React settle before re-querying.
- **`activationConstraint` may vary** — `distance: 4` is the value in `SortableFreshList.tsx`. If a different component uses `delay`-based activation instead, increase the delay between steps 1 and 2 accordingly.
- **Vertical-axis modifier** — `SortableFreshList.tsx` uses `verticalAxisOnly` (zeroes x delta). The x coordinate in `pointermove` steps doesn't matter for this component, but keeping `ex` in step 4 is harmless.

## Verified on

- Component: `SortableFreshList.tsx` (PR #10409, SUP-7717)
- Library: `@dnd-kit/core` + `@dnd-kit/sortable`
- Sensor: `PointerSensor` with `activationConstraint: { distance: 4 }`
- Results: panel order updated ✅, PATCH 200 ✅, screen reader announcement ✅
