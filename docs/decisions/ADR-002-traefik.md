# ADR-002: Use Traefik inside the AI VM

**Status:** Accepted

## Context

The stack contains multiple Docker services and will use internal HTTPS. Caddy is simpler for static routes; Nginx offers deep manual control. Traefik provides Docker label discovery and clean service-local routing.

## Decision

Run one Traefik instance in the AI VM. Publish only ports 80 and 443 on the VM address. Set `exposedByDefault=false`.

## Consequences

- Routes are co-located with Compose definitions.
- Another Traefik instance can safely run on another VM.
- Docker socket access must be treated as privileged; later hardening should introduce a restricted socket proxy.
