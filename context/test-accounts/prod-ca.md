# Prod-CA External Test Account

## Account — GhostPractice-enabled external (Canada)

- **Email**: `regression@test.com`
- **Role**: `external`
- **Environment**: `prod-ca`
- **Portal URL**: `ca-portal.supio.com`
- **Company**: "QA Test Canadian Company" (`company_id=39`)
- **Config key**: `external[tags=ghostpractice]` in `config/env.ca.json`
- **Connectors**: GhostPractice — **Connected** (confirmed via Connectors dialog)

## When to use

Use `regression@test.com` on `prod-ca` whenever a ticket:

- Is GhostPractice-specific (skill gated with `firmGated:[ghostpractice]`)
- Targets the `prod-ca` environment explicitly (Canadian tenant, `ca-portal.supio.com`)
- Requires a live GhostPractice connector for `connector_request(target="external")` calls

## Feature flags on prod-ca

`feature-case-agent` is **not** provisioned in backend `enabled_feature_flags` for this account on prod-ca. To enable the Case Agent chat UI:

1. Open DevTools → Application → Local Storage → `ca-portal.supio.com`
2. Edit `enabledFeatureFlags` — append `,feature-case-agent` to the existing value
   - Example: `poc-rc,feature-ghost-practice` → `poc-rc,feature-ghost-practice,feature-case-agent`
3. Reload the page

Log this as a `feature_flag_preflight` trace event with `runtime_override: applied_via_localStorage`.

## Choosing this account vs prod external accounts

| Scenario | Account |
|----------|---------|
| GhostPractice skill or connector scenarios | `regression@test.com` on `prod-ca` |
| Non-GhostPractice connector scenarios (Clio, SmartAdvocate, CasePeer, etc.) | `user@test.supio` on `prod` |
| No-connector / firm-gating / teams scenarios | `teamQAadmin@test.com` on `prod` |

## Credential storage

Credentials are stored in `config/env.ca.json`. Never echo passwords in chat, logs, artifacts, or commits.
