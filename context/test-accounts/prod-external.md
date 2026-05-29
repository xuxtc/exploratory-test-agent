# Prod External Test Accounts

There are **two** prod external accounts. See each account's section for connector availability.

## Account A — connector-enabled external

- **Email**: `user@test.supio`
- **Role**: `external`
- **Environment**: `prod`
- **Config key**: `prod.external` in `config/env.prod.json`
- **Connectors**: has **most connectors configured** (SmartAdvocate, CasePeer, Clio, etc.)
- **Use when**: ticket requires connector-positive scenarios (e.g. connector tools available, connector-case-facts populated, PMS data visible)

## Account B — no-connector + teams-enabled external

- **Email**: `teamQAadmin@test.com`
- **Role**: `external` (FIRM_ADMIN on "QA Test Team Company")
- **Environment**: `prod`
- **Config key**: `external[tags=teams]` in `config/env.prod.json`
- **Connectors**: **NO connectors configured**
- **Use when**:
  - Negative / firm-gating tests (verifying connector-dependent features are absent on a non-connector firm)
  - Tickets that require teams features (team management, teams feature flag)
  - Any ticket whose triage assigns `user_role: external` and does NOT require an active connector

## Choosing the right account

| Scenario | Account |
|----------|---------|
| Connector-positive AC (e.g. Smokeball tools work, connector_request returns data) | `user@test.supio` |
| Connector-negative / firm-gating (e.g. Smokeball tools absent on non-Smokeball firm) | `teamQAadmin@test.com` |
| Teams features (team management, teams flag) | `teamQAadmin@test.com` |
| General non-connector external scenarios | `teamQAadmin@test.com` (preferred — no connector noise) |

## Handling Smokeball-specific tickets

`user@test.supio` has most connectors but may not have **SmokeballDirect** configured. Before running Smokeball-positive scenarios, verify whether this account's firm has SmokeballDirect active. If not, those scenarios remain `blocked_no_fixture`.

## When NOT to use these accounts

- `user_role: internal` scenarios — use the designated internal test company (57blocks / Supio tenant) instead.

## Credential storage

Credentials are stored in `config/env.prod.json`. Never echo passwords in chat, logs, artifacts, or commits.

## Connector matter IDs for test data

When writing specs or data plans for connector-linked case creation, use the IDs in [`connector-matter-ids.md`](connector-matter-ids.md). That file lists one `external_case_id` per connector available on `user@test.supio`.

## Handling connector-dependent tickets

When a ticket requires connector-specific positive scenarios and the required connector is not available on any test account:

1. Mark those scenarios as `blocked_no_fixture` in the spec (`data_confidence: low`, `case_decision: blocked_no_fixture`).
2. Execute only the negative / firm-gating scenarios using `teamQAadmin@test.com`.
3. Note in the Linear report that positive connector scenarios are deferred.
