# Security

## Intended exposure

The system is available only from trusted internal networks or an approved VPN.

### Ubiquiti firewall policy

| Source | Destination | Service | Action |
|---|---|---|---|
| Trusted LAN | AI VM | TCP 443 | Allow |
| Admin LAN/VLAN | AI VM | TCP 22 | Allow |
| AI VM | DNS/NTP | required ports | Allow |
| AI VM | Synology backup target | backup protocol | Allow |
| AI VM | Internet | TCP 443 | Allow for controlled updates/downloads |
| Guest VLAN | AI VM | Any | Deny |
| IoT VLAN | AI VM | Any | Deny |
| WAN | AI VM | Any | Deny |

Do not create WAN port forwards.

## Identity

- Disable uncontrolled local signup.
- Use Authentik OIDC.
- Place the owner in `ai-admins`.
- Place the second user in `ai-users`.
- Enable MFA for administrators.
- Retain one tested emergency recovery method.
- Do not make the second user an Open WebUI administrator.

## Application permissions

Open WebUI should enforce:

- administrator-only model management;
- administrator-only shared-knowledge changes;
- private personal memory;
- private user knowledge;
- approved model access for standard users;
- no arbitrary external API endpoints for standard users.

## Container exposure

Only Traefik publishes host ports.

Never add:

```yaml
ports:
  - "11434:11434"
```

to Ollama, or a PostgreSQL host port.

## Docker socket

The baseline uses a read-only Docker socket mount for Traefik. Read-only does not make Docker API access harmless. A hardened revision should use a dedicated Docker socket proxy that permits only the endpoints Traefik needs.

## TLS

Use either:

- a real owned domain with internal split DNS and DNS challenge; or
- an internal certificate authority whose root certificate is installed on trusted clients.

Do not disable TLS to work around OIDC errors.

## Secrets

- Generate unique random values.
- Keep `.env` mode `0600`.
- Do not commit `.env`.
- Do not paste secrets into issues or logs.
- Store the backup password separately from the backup repository.
- Rotate OIDC and database secrets after suspected exposure.

## LLM-specific controls

- Do not place passwords or private keys in memory.
- Treat uploaded documents as untrusted input.
- Do not grant models autonomous shell or network tools by default.
- Review third-party Open WebUI functions before installation.
- Avoid cloud model endpoints unless a later decision explicitly approves them.
