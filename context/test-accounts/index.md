# Test Accounts

This directory documents the shared test accounts used across environments and roles.

| Account | Role | Environment | Notes |
|---------|------|-------------|-------|
| `user@test.supio` | external | prod | Has most connectors (SmartAdvocate, CasePeer, Clio, etc.); use for connector-positive scenarios |
| `teamQAadmin@test.com` | external (teams) | prod | NO connectors; teams-enabled; use for firm-gating / no-connector / teams scenarios |
| internal test company | internal | prod | 57blocks / Supio tenant |
| "QA Test Team Company" | team | prod | FIRM_ADMIN on teams-enabled company |
| `regression@test.com` | external | prod-ca | GhostPractice Connected; "QA Test Canadian Company" (company_id=39); use for GhostPractice-specific and prod-ca scenarios |

See each detail file for credentials location, company context, and usage rules.

- [prod-external.md](prod-external.md) — both prod external accounts (`user@test.supio` + `teamQAadmin@test.com`)
- [prod-ca.md](prod-ca.md) — prod-ca external account (`regression@test.com`)
- [connector-matter-ids.md](connector-matter-ids.md) — test matter IDs per connector for `create_case` connector-linkage scenarios (Litify, SmartAdvocate, Filevine)
