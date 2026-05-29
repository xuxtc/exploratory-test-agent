# Timeline Extraction Flow (Updated 2026-05-25)

## Change

Timeline extraction **no longer triggers automatically** after file upload.

The executor must explicitly ask the Case Agent to generate the timeline before polling medical-chronology.

## Required steps (after case creation and file upload)

1. Navigate to the case page (any tab, e.g. `/cases/<id>/medical-chronology`).
2. The Agent chat panel opens on the left. Type and send: **"generate timeline"**
3. Wait for the Agent to respond with "Timeline generated — N events committed across M dates."
4. Only then start polling medical-chronology for extracted events.

## What happens without this step

The medical-chronology page shows "No events found" indefinitely — files are in CASE FILES but extraction never starts unless the agent is invoked.

## Evidence

Observed during DEX-2849 run (2026-05-25_1424_DEX-2849): case 8755324 had files uploaded but showed "No events found" for 220+ seconds until "generate timeline" was sent to the agent.
