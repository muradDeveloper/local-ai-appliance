# ADR-004: PostgreSQL from first deployment

**Status:** Accepted

## Decision

Use PostgreSQL for Open WebUI and Authentik, with separate databases and credentials.

## Rationale

It avoids a later SQLite-to-PostgreSQL migration and supports reliable logical backups.

## Consequences

- Database lifecycle must be maintained.
- Upgrade and restore procedures must include PostgreSQL.
- Database ports remain private.
