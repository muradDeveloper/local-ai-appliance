# Threat model

## Assets

- user identities;
- administrator credentials;
- personal chat history;
- personal long-term memory;
- private and shared knowledge;
- database contents;
- TLS and OIDC secrets;
- GPU compute availability.

## Likely threats

- accidental WAN exposure;
- compromised internal client;
- malicious document prompt injection;
- weak administrator authentication;
- over-permissive Open WebUI role;
- Docker socket compromise;
- untested backup;
- secret committed to Git;
- model/tool granted excessive host access.

## Primary mitigations

- deny WAN and untrusted VLANs;
- internal HTTPS;
- Authentik MFA;
- least-privilege Open WebUI groups;
- no autonomous host tools by default;
- private Docker networks;
- encrypted backups;
- restore testing;
- code review for Compose and scripts;
- secrets excluded from Git.
