/**
 * dnd-kit PointerSensor drag simulation for SortableFreshList.tsx
 *
 * Status: VERIFIED working
 *   - Panel order updates correctly in React UI
 *   - dnd-kit screen reader announces the drop
 *   - PATCH /api/v1/task-lists/:id/items returns 200
 *
 * Library internals confirmed from source:
 *   @dnd-kit/core PointerSensor
 *   - Activator: onPointerDown on drag handle element
 *   - Listeners added to document: pointermove, pointerup, pointercancel
 *   - DistanceConstraint: { distance: 4 } — need > 4px move to activate
 *   - verticalAxisOnly modifier: x delta zeroed, only y matters
 *
 * DOM structure (confirmed):
 *   button[aria-label="Drag to reorder"]   ← handle (level 0)
 *     -> parentElement                      ← level 1 (inner div)
 *     -> parentElement.parentElement        ← level 2 = row div, textContent = task name
 *
 * Simulation sequence:
 *   1. pointerdown  on handle element  (attaches dnd-kit document listeners)
 *   2. pointermove  on document +6px y (exceeds 4px DistanceConstraint → drag activates)
 *   3. pointermove  on document midpoint (smooth trajectory, optional)
 *   4. pointermove  on document at target coords (sets drop target)
 *   5. pointerup    on document (fires handleDragEnd → onReorder callback → PATCH)
 *
 * Usage in evaluate_script:
 *
 *   return await simulateDndKitDrag({ sourceIndex: 0, targetIndex: 2 });
 *
 * sourceIndex / targetIndex: 0-based positions among visible drag handles.
 * Drag from sourceIndex to targetIndex. The item at sourceIndex moves to
 * the position of targetIndex; items in between shift by one.
 */
async function simulateDndKitDrag({ sourceIndex, targetIndex }) {
  const LABEL = 'Drag to reorder';
  const handles = Array.from(document.querySelectorAll(`button[aria-label="${LABEL}"]`));

  if (handles.length === 0)
    return { error: `No drag handles found with aria-label="${LABEL}"` };
  if (sourceIndex >= handles.length || targetIndex >= handles.length)
    return { error: `Index out of range — found ${handles.length} handles, got source=${sourceIndex} target=${targetIndex}` };

  // Row text extraction: handle → div → div (level 2 = row container)
  function readOrder() {
    return Array.from(document.querySelectorAll(`button[aria-label="${LABEL}"]`))
      .map(h => {
        const row = h.parentElement?.parentElement;
        const text = row?.textContent?.trim() ?? '';
        // Extract task name — everything up to "Supio" or end of string
        return text.match(/^(deqtest_\S+?_\S+?_\S+?)(?:Supio|$)/)?.[1]
          ?? text.substring(0, 25);
      });
  }

  const srcRect = handles[sourceIndex].getBoundingClientRect();
  const tgtRect  = handles[targetIndex].getBoundingClientRect();
  const sx = srcRect.left + srcRect.width  / 2;
  const sy = srcRect.top  + srcRect.height / 2;
  const ex = tgtRect.left + tgtRect.width  / 2;
  const ey = tgtRect.top  + tgtRect.height / 2;

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

  // 1. Activate sensor
  handles[sourceIndex].dispatchEvent(ptr('pointerdown', sx, sy));
  await delay(30);

  // 2. Exceed 4px distance constraint → drag starts
  document.dispatchEvent(ptr('pointermove', sx, sy + 6));
  await delay(30);

  // 3. Move toward target (intermediate step for smoother trajectory)
  document.dispatchEvent(ptr('pointermove', sx, (sy + ey) / 2));
  await delay(30);

  // 4. Arrive at target
  document.dispatchEvent(ptr('pointermove', ex, ey));
  await delay(50);

  // 5. Release → handleDragEnd → onReorder → PATCH /api/v1/task-lists/:id/items
  document.dispatchEvent(ptr('pointerup', ex, ey));
  await delay(150);

  const after = readOrder();

  return {
    ok: true,
    handlesFound: handles.length,
    sourceIndex,
    targetIndex,
    coords: { sx, sy, ex, ey },
    before,
    after,
    changed: JSON.stringify(before) !== JSON.stringify(after),
  };
}

return await simulateDndKitDrag({ sourceIndex: 0, targetIndex: 2 });
