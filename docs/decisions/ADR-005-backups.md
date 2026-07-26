# ADR-005: Layered backups

**Status:** Accepted

## Decision

Use nightly application backups to Synology and weekly VM backups to PBS.

## Rationale

Logical database dumps and files support granular restore. PBS supports rapid whole-VM disaster recovery. Neither layer replaces the other.

## Consequences

- Backups must be tested.
- Model blobs are normally excluded.
- Secrets are included only in encrypted storage.
