# ADR-003: Authentik through native OIDC

**Status:** Accepted

## Decision

Open WebUI authenticates directly against Authentik through OIDC.

## Rationale

Native OIDC conveys the user identity to Open WebUI and allows Open WebUI to maintain its own roles, groups and resource permissions. Proxy forward-auth is reserved for applications without native SSO support.

## Consequences

- Callback URL and issuer URLs must be correct and HTTPS.
- Authentik is responsible for account security and MFA.
- Open WebUI remains responsible for authorisation.
