# Portal Routes: Inbox surfaces

## When this rule applies

When a ticket mentions "inbox", "folder rail", "Outlook folders", "mailroom", or any `/inbox` URL — or when a PR touches `equity-gateway`'s Outlook connector routes.

## Two distinct "inbox" surfaces

| Route | Name | What it is | Outlook folder rail? |
|-------|------|-----------|----------------------|
| `/inbox` | Global Outlook Inbox | Account-level Outlook email client. Shows the folder rail (Inbox, Sent, Drafts, Archive, Junk, Deleted as pinned system row + user FOLDERS below). Powered by `equity-gateway GET /outlook/folders`. | **Yes — this is the one.** |
| `/cases/<id>/inbox` | Case Mailroom | Per-case document-upload inbox. Receives files sent to the firm's Supio email address and associates them with the case. Completely unrelated to Outlook. | No — shows "Upload files" + document list. |

## Outlook connection scope

- Outlook is connected at the **account level** (per-user), not per-case.
- Connection status visible at `/api/v3/agentic-connector/me` → `connections[].provider === "outlook"`.
- The `feature-outlook` flag must be enabled for the account for the `/inbox` rail to render.
- Any account with an active Outlook OAuth token will see the folder rail at `/inbox` — no specific case setup required.

## equity-gateway route

`GET /equity-gateway/connectorv3/outlook/folders` is called by the portal when loading `/inbox`. This is the backend route that SUP-7788 fixes (well-known folder classification). The call is **not** triggered by `/cases/<id>/inbox`.

## Known interactions

- SUP-7788 — fixes sporadic well-known folder misclassification in the folder rail at `/inbox`. Tested by navigating to `/inbox` directly as an account with Outlook connected.
- Per-case Mailroom (`/cases/<id>/inbox`) will show a blank/loading state when no Mailroom configuration exists — this is expected and unrelated to Outlook connectivity.
