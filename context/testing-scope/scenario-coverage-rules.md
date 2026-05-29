# Scenario Coverage Rules

These rules apply to **any agent or skill that designs test scenarios from a Linear ticket and its PR diff** — including `test-strategist` (Requirement Spec) and `analyze-tickets` (bilingual test case table). Both must produce the same scenario coverage for the same ticket.

---

## Rule 1 — One scenario per code entry point

If a ticket's PR diff modifies N distinct entry points (e.g. `archiveCase`, `bulkArchiveCases`, `adminArchiveCase`), there must be N corresponding scenarios — one per entry point. Do not merge them into a single scenario or mention them only in prose.

This is a hard coverage floor: if you can count N entry points in the diff, the output must have ≥ N scenarios covering them.

**UI reachability gate (applied before counting entry points):** An entry point only counts toward the coverage floor if a human tester can reach it by operating the browser UI. Entry points that are exclusively reachable via:
- backend schema validation with no user-visible response (pure server-side rejection with no UI feedback)
- API-only or CLI-only paths with no UI affordance

must be moved to **Out of scope** with the note `"backend/agent-internal validation — covered by unit tests in <file>"`. Do not write a UI scenario for them.

**Case Agent chat is a UI surface.** When the product uses a Case Agent chat interface, validation errors triggered by agent tool calls (e.g. mutual-presence checks on `create_case` args) ARE UI-reachable — the user can send a natural-language prompt that causes the agent to attempt the invalid call, and the error surfaces as a visible chat response. These scenarios must be included, not moved to Out of scope.

**How to apply:** For each entry point found in the diff, ask: "Can a human tester trigger this code path and observe the result by operating the browser UI — including via chat prompts to an AI agent?" If no → Out of scope. If yes → write a scenario.

---

## Rule 2 — PR description's reported issue must become an end-to-end scenario

The "reported issue" / "root cause" / "problem" section of the PR body describes what the user actually experienced. Extract at least one scenario that validates the fix from the user's perspective (e.g. "case no longer appears in To-Do queue") — not just a field-value assertion (e.g. "Econ status = Published").

Field-level verification alone is insufficient as a standalone scenario; it must be paired with a user-observable behavioral check.

---

## Rule 3 — CTA side-effect isolation

When a component has two or more interactive controls (e.g. an action button + a close/dismiss button), each control must have its own scenario. One scenario must explicitly verify that triggering control A does **not** produce the side effects of control B.

This applies to any Alert / Dialog / Toast / Banner / Modal that carries both an action and a dismiss control. If the PR diff introduces or modifies such a component and the output has only one scenario covering it, that is a coverage gap.

---

## Rule 4 — Order and group scenarios by test data lifecycle (hard rule)

When multiple scenarios depend on the same test data object (e.g. a case, a connector linkage, a document, a session), they must be arranged in the order the data naturally passes through its states, and grouped into a single ordered sequence:

1. **Create / establish** the data first — this scenario verifies the creation behavior (primary path).
2. **Operate on** the established data — these scenarios verify behavior against existing data (e.g. dedup, conflict detection, update, deletion).
3. **Destroy / clean up** only if required by a specific AC.

**This is a hard rule — no exceptions.** A scenario that says "given data X already exists" and relies on X having been created by a prior independent run is forbidden. Every scenario sequence must be self-contained: it creates its own prerequisite data within the same session before asserting behavior that depends on it.

**How to apply:** Before writing any scenario whose Given clause references a data object, ask: "Does another scenario in this spec create that object?" If yes — that scenario must run first in the same ordered sequence. Merge them into one sequence rather than two independent scenarios. If the creation scenario is out of scope for this ticket, note it explicitly in **Out of scope** and mark the dependent scenario as `data_confidence: low` with a `data_blocker` explaining what needs to be created first.
